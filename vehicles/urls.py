from django.urls import path

from . import views

app_name = "vehicles"

urlpatterns = [
    path("", views.vehicle_list, name="list"),
    path("new/", views.vehicle_create, name="create"),
    path("vin-lookup/", views.vin_lookup, name="vin_lookup"),
    path("makes.json", views.makes_json, name="makes_json"),
    path("models.json", views.models_json, name="models_json"),
    path("<int:pk>/", views.vehicle_detail, name="detail"),
    path("<int:pk>/recalls.json", views.recalls_data, name="recalls_data"),
    path("<int:pk>/specs.json", views.specs_data, name="specs_data"),
    path("<int:pk>/safety.json", views.safety_data, name="safety_data"),
    path("<int:pk>/model-summary.json", views.model_summary_data, name="model_summary_data"),
    path("<int:vehicle_pk>/reminders/new/", views.reminder_create, name="reminder_create"),
    path("reminders/<int:pk>/mark-done/", views.reminder_mark_done, name="reminder_mark_done"),
    path("<int:pk>/qr-code.png", views.vehicle_qr_code, name="qr_code"),
    path("service-history/<uuid:token>/", views.service_history, name="service_history"),
]
