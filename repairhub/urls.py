from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from core.views import TwoFactorLoginView, two_factor_verify

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", TwoFactorLoginView.as_view(), name="login"),
    path("login/verify/", two_factor_verify, name="two_factor_verify"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("core.urls")),
    path("vehicles/", include("vehicles.urls")),
    path("diagnostics/", include("diagnostics.urls")),
    path("guides/", include("repairguides.urls")),
    path("shop/", include("shop.urls")),
    path("integrations/", include("integrations.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
