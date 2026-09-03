from django.urls import path

from . import views

app_name = "diagnostics"

urlpatterns = [
    path("", views.dtc_list, name="list"),
    path("import/", views.import_codes_view, name="import"),
    path("<str:code>/", views.dtc_detail, name="detail"),
]
