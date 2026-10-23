from django import forms
from django.utils import timezone
from .models import Category, CatalogItem, EquipmentUnit
import re

class BootstrapMixin:
    def _style(self):
        for field in self.fields.values():
            css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs["class"] = css


class CategoryForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        qs = Category.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("A category with this name already exists.")
        return name


class CatalogItemForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = CatalogItem
        fields = ["category", "name", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Category.objects.filter(is_archived=False)
        if self.instance.pk:
            qs = Category.objects.filter(pk=self.instance.category_id) | qs
        self.fields["category"].queryset = qs.distinct().order_by("name")
        
        self.fields["category"].label_from_instance = lambda obj: obj.name
        self._style()

    def clean(self):
        cleaned = super().clean()
        category = cleaned.get("category")
        name = (cleaned.get("name") or "").strip()
        if category and name:
            qs = CatalogItem.objects.filter(category=category, name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error("name", "This item already exists in that category.")
            cleaned["name"] = name
        return cleaned

def next_asset_code(prefix="ASSET"):
    last = 0
    for code in EquipmentUnit.objects.filter(
            asset_code__startswith=f"{prefix}-").values_list("asset_code", flat=True):
        m = re.fullmatch(rf"{prefix}-(\d+)", code)
        if m:
            last = max(last, int(m.group(1)))
    return f"{prefix}-{last + 1:04d}"

class EquipmentUnitForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = EquipmentUnit
        fields = ["catalog_item", "asset_code", "condition", "acquisition_date"]
        widgets = {"acquisition_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = CatalogItem.objects.filter(is_archived=False)
        if self.instance.pk:
            qs = CatalogItem.objects.filter(pk=self.instance.catalog_item_id) | qs
        self.fields["catalog_item"].queryset = (
            qs.select_related("category").distinct().order_by("category__name", "name")
        )
        self.fields["catalog_item"].label_from_instance = (
            lambda obj: f"{obj.name} ({obj.category.name})"
        )
        if self.instance.pk:
            self.fields["asset_code"].disabled = True
            self.fields["catalog_item"].disabled = True
            
        if not self.instance.pk and not self.is_bound:
            self.fields["asset_code"].initial = next_asset_code()
            self.fields["asset_code"].help_text = (
                "Suggested automatically. Change it to match the label on the equipment.")
        self._style()

    def clean_asset_code(self):
        code = self.cleaned_data["asset_code"].strip().upper()
        qs = EquipmentUnit.objects.filter(asset_code__iexact=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("This asset code is already registered.")
        return code

    def clean_acquisition_date(self):
        d = self.cleaned_data["acquisition_date"]
        if d > timezone.localdate():
            raise forms.ValidationError("Acquisition date cannot be in the future.")
        return d