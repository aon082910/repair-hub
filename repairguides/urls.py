from django.urls import path

from . import views

app_name = "repairguides"

urlpatterns = [
    path("", views.guide_list, name="list"),
    path("import/", views.import_guides_view, name="import"),
    path("external-search/", views.external_search, name="external_search"),
    path("external-search.json", views.external_search_json, name="external_search_json"),
    path("commons-search.json", views.commons_search_json, name="commons_search_json"),
    path("wiring-diagrams/", views.wiring_diagram_list, name="wiring_list"),
    path("<int:pk>/", views.guide_detail, name="detail"),
]
