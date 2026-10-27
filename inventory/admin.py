from django.contrib import admin
from django.apps import apps

# This automatically registers every model in your 'inventory' app
app = apps.get_app_config('inventory')

for model_name, model in app.models.items():
    try:
        admin.site.register(model)
    except admin.sites.AlreadyRegistered:
        pass