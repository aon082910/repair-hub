from django.urls import path

from . import views

app_name = "integrations"

urlpatterns = [
    path("vehicles/<int:vehicle_pk>/add-link/", views.add_link, name="add_link"),
    path("vehicles/<int:vehicle_pk>/add-attachment/", views.add_attachment, name="add_attachment"),
]
