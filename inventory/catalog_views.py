from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .catalog_forms import CategoryForm, CatalogItemForm, EquipmentUnitForm
from .decorators import admin_required
from .models import AuditLog, CatalogItem, Category, EquipmentUnit

T = "admin/catalog/"


def log(request, action, obj):
    AuditLog.objects.create(
        actor=request.user,
        action=action,
        record_reference=f"{obj.__class__.__name__} #{obj.pk}: {obj}",
    )


def paginate(request, qs, per_page=5):
    page_obj = Paginator(qs, per_page).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return page_obj, params.urlencode()


def tab_counts():
    return {"category_total": Category.objects.count(),
            "item_total": CatalogItem.objects.count()}


def apply_status(qs, status):
    if status == "active":
        return qs.filter(is_archived=False)
    if status == "archived":
        return qs.filter(is_archived=True)
    return qs


#Modal helpers
def is_ajax(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def form_page(request, form, title, cancel_name):
    ctx = {"form": form, "title": title, "cancel_url": reverse(cancel_name)}
    if is_ajax(request):
        return render(request, T + "_form_modal_body.html", ctx)  
    return render(request, T + "form.html", ctx)                 


def form_saved(request, redirect_name):
    if is_ajax(request):
        return JsonResponse({"ok": True})                         
    return redirect(redirect_name)


# Categories
@admin_required
def category_list(request):
    q = request.GET.get("q", "").strip()
    qs = Category.objects.annotate(
    item_count=Count("catalogitem", filter=Q(catalogitem__is_archived=False))
).order_by("-id")
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
    page_obj, querystring = paginate(request, qs, per_page=5)
    return render(request, T + "category_list.html", {
        "page_obj": page_obj, "querystring": querystring, "q": q,
        **tab_counts(),
    })


@admin_required
def category_create(request):
    form = CategoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        category = form.save()
        log(request, "CATEGORY_CREATED", category)
        messages.success(request, "Category created.")
        return form_saved(request, "catalog:category_list")
    return form_page(request, form, "New Category", "catalog:category_list")


@admin_required
def category_detail(request, pk):
    category = get_object_or_404(Category, pk=pk)
    items = (CatalogItem.objects.filter(category=category)
             .annotate(unit_count=Count("equipmentunit", filter=~Q(equipmentunit__inventory_status="Retired")))
             .order_by("name"))
    return render(request, T + "category_detail.html", {"category": category, "items": items})


@admin_required
def category_update(request, pk):
    category = get_object_or_404(Category, pk=pk)
    form = CategoryForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        form.save()
        log(request, "CATEGORY_UPDATED", category)
        messages.success(request, "Category updated.")
        return form_saved(request, "catalog:category_list")
    return form_page(request, form, "Edit Category", "catalog:category_list")


@admin_required
def category_archive(request, pk):
    category = get_object_or_404(Category, pk=pk)
    active_items = category.catalogitem_set.filter(is_archived=False).count()
    if request.method == "POST":
        if active_items:
            messages.error(request, "Cannot archive: this category still has active items.")
        else:
            category.is_archived = True
            category.save(update_fields=["is_archived"])
            log(request, "CATEGORY_ARCHIVED", category)
            messages.success(request, f"Category '{category.name}' archived.")
        return redirect("catalog:category_list")
    blocked = (f"This category still has {active_items} active item(s). Archive them first."
               if active_items else "")
    return render(request, T + "confirm_archive.html", {
        "object": category, "kind": "category", "blocked": blocked,
        "cancel_url": reverse("catalog:category_list")})


@admin_required
@require_POST
def category_restore(request, pk):
    category = get_object_or_404(Category, pk=pk)
    category.is_archived = False
    category.save(update_fields=["is_archived"])
    log(request, "CATEGORY_RESTORED", category)
    messages.success(request, f"Category '{category.name}' restored.")
    return redirect("catalog:category_list")


# Catalog items
@admin_required
def item_list(request):
    q = request.GET.get("q", "").strip()
    category_id = request.GET.get("category", "")
    qs = (CatalogItem.objects.select_related("category")
      .annotate(
          unit_count=Count("equipmentunit", filter=~Q(equipmentunit__inventory_status="Retired")),
          in_use=Count("equipmentunit", filter=Q(equipmentunit__inventory_status__in=["Reserved", "Issued"])),
      )
      .order_by("-id"))
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q) | Q(category__name__icontains=q))
    if category_id.isdigit():
        qs = qs.filter(category_id=category_id)
    page_obj, querystring = paginate(request, qs, per_page=5)
    return render(request, T + "item_list.html", {
        "page_obj": page_obj, "querystring": querystring, "q": q,
        "category_id": category_id, "categories": Category.objects.order_by("name"),
        **tab_counts(),
    })


@admin_required
def item_detail(request, pk):
    item = get_object_or_404(CatalogItem.objects.select_related("category"), pk=pk)
    units = EquipmentUnit.objects.filter(catalog_item=item).order_by("asset_code")
    counts = dict(units.order_by().values_list("inventory_status").annotate(n=Count("id")))
    unit_counts = [(label, counts.get(value, 0)) for value, label in EquipmentUnit.STATUS_CHOICES]
    return render(request, T + "item_detail.html", {
        "item": item, "units": units, "unit_counts": unit_counts})


@admin_required
def item_create(request):
    form = CatalogItemForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        item = form.save()
        log(request, "CATALOG_ITEM_CREATED", item)
        messages.success(request, "Catalog item created.")
        return form_saved(request, "catalog:item_list")
    return form_page(request, form, "New Catalog Item", "catalog:item_list")


@admin_required
def item_update(request, pk):
    item = get_object_or_404(CatalogItem, pk=pk)
    form = CatalogItemForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        form.save()
        log(request, "CATALOG_ITEM_UPDATED", item)
        messages.success(request, "Catalog item updated.")
        return form_saved(request, "catalog:item_list")
    return form_page(request, form, "Edit Catalog Item", "catalog:item_list")


@admin_required
def item_archive(request, pk):
    item = get_object_or_404(CatalogItem, pk=pk)
    in_use = EquipmentUnit.objects.filter(
        catalog_item=item, inventory_status__in=["Reserved", "Issued"]).count()
    if request.method == "POST":
        if in_use:
            messages.error(request, "Cannot archive: some units are reserved or issued.")
        else:
            item.is_archived = True
            item.save(update_fields=["is_archived"])
            log(request, "CATALOG_ITEM_ARCHIVED", item)
            messages.success(request, f"Catalog item '{item.name}' archived.")
        return redirect("catalog:item_list")
    blocked = (f"{in_use} unit(s) are currently reserved or issued. Wait until they are returned."
               if in_use else "")
    return render(request, T + "confirm_archive.html", {
        "object": item, "kind": "catalog item", "blocked": blocked,
        "cancel_url": reverse("catalog:item_list")})


@admin_required
@require_POST
def item_restore(request, pk):
    item = get_object_or_404(CatalogItem, pk=pk)
    if item.category.is_archived:
        messages.error(request, "Restore its category first.")
    else:
        item.is_archived = False
        item.save(update_fields=["is_archived"])
        log(request, "CATALOG_ITEM_RESTORED", item)
        messages.success(request, f"Catalog item '{item.name}' restored.")
    return redirect("catalog:item_list")


# Physical units
@admin_required
def unit_list(request):
    q = request.GET.get("q", "").strip()
    category_id = request.GET.get("category", "")
    item_id = request.GET.get("item", "")
    status = request.GET.get("status", "")
    qs = EquipmentUnit.objects.select_related("catalog_item__category").order_by("-id")
    if q:
        qs = qs.filter(asset_code__icontains=q)
    if category_id.isdigit():
        qs = qs.filter(catalog_item__category_id=category_id)
    if item_id.isdigit():
        qs = qs.filter(catalog_item_id=item_id)
    if status in dict(EquipmentUnit.STATUS_CHOICES):
        qs = qs.filter(inventory_status=status)
    page_obj, querystring = paginate(request, qs)
    return render(request, T + "unit_list.html", {
        "page_obj": page_obj, "querystring": querystring, "q": q,
        "category_id": category_id, "item_id": item_id, "status": status,
        "categories": Category.objects.order_by("name"),
        "items": CatalogItem.objects.order_by("name"),
        "status_choices": EquipmentUnit.STATUS_CHOICES})


@admin_required
def unit_create(request):
    form = EquipmentUnitForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        unit = form.save(commit=False)
        unit.inventory_status = "Available"    
        unit.save()
        log(request, "UNIT_REGISTERED", unit)
        messages.success(request, f"Unit {unit.asset_code} registered.")
        return form_saved(request, "catalog:unit_list")
    return form_page(request, form, "Register Unit", "catalog:unit_list")


@admin_required
def unit_update(request, pk):
    unit = get_object_or_404(EquipmentUnit, pk=pk)
    form = EquipmentUnitForm(request.POST or None, instance=unit)
    if request.method == "POST" and form.is_valid():
        form.save()
        log(request, "UNIT_UPDATED", unit)
        messages.success(request, "Unit updated.")
        return form_saved(request, "catalog:unit_list")
    return form_page(request, form, f"Edit Unit {unit.asset_code}", "catalog:unit_list")


@admin_required
def unit_retire(request, pk):
    unit = get_object_or_404(EquipmentUnit, pk=pk)
    blocked = ""
    if unit.inventory_status in ("Reserved", "Issued"):
        blocked = f"This unit is {unit.inventory_status.lower()} and cannot be retired now."
    elif unit.inventory_status == "Retired":
        blocked = "This unit is already retired."
    if request.method == "POST":
        if blocked:
            messages.error(request, blocked)
        else:
            unit.inventory_status = "Retired"
            unit.save(update_fields=["inventory_status"])
            log(request, "UNIT_RETIRED", unit)
            messages.success(request, f"Unit {unit.asset_code} retired.")
        return redirect("catalog:unit_list")
    return render(request, T + "confirm_archive.html", {
        "object": unit, "kind": "unit", "action": "retire", "blocked": blocked,
        "cancel_url": reverse("catalog:unit_list")})