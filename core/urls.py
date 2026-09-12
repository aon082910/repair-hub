from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("favorites/", views.favorites_list, name="favorites"),
    path("favorites/toggle/", views.toggle_favorite, name="toggle_favorite"),
    path("search/", views.global_search, name="global_search"),
    path("backup/", views.download_backup, name="download_backup"),
    path("account/2fa/", views.two_factor_setup, name="two_factor_setup"),
    path("account/2fa/qr-code.png", views.two_factor_qr_code, name="two_factor_qr_code"),
    path("account/2fa/disable/", views.two_factor_disable, name="two_factor_disable"),
]
