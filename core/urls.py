from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("favorites/", views.favorites_list, name="favorites"),
    path("favorites/toggle/", views.toggle_favorite, name="toggle_favorite"),
    path("search/", views.global_search, name="global_search"),
    path("backup/", views.download_backup, name="download_backup"),
]
