from django.urls import path
from . import catalog_views as v

app_name = "catalog"

urlpatterns = [
    path("categories/", v.category_list, name="category_list"),
    path("categories/new/", v.category_create, name="category_create"),
    path("categories/<int:pk>/", v.category_detail, name="category_detail"),
    path("categories/<int:pk>/edit/", v.category_update, name="category_update"),
    path("categories/<int:pk>/archive/", v.category_archive, name="category_archive"),
    path("categories/<int:pk>/restore/", v.category_restore, name="category_restore"),

    path("items/", v.item_list, name="item_list"),
    path("items/new/", v.item_create, name="item_create"),
    path("items/<int:pk>/", v.item_detail, name="item_detail"),
    path("items/<int:pk>/edit/", v.item_update, name="item_update"),
    path("items/<int:pk>/archive/", v.item_archive, name="item_archive"),
    path("items/<int:pk>/restore/", v.item_restore, name="item_restore"),

    path("units/", v.unit_list, name="unit_list"),
    path("units/new/", v.unit_create, name="unit_create"),
    path("units/<int:pk>/edit/", v.unit_update, name="unit_update"),
    path("units/<int:pk>/retire/", v.unit_retire, name="unit_retire"),
]