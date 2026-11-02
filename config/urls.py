from django.contrib import admin
from django.urls import include, path

from recruiting.views import landing

urlpatterns = [
    path("", landing, name="landing"),
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("recruiting.urls")),
]
