from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from rest_framework import routers
from api import views

router = routers.DefaultRouter()
router.register(r"users", views.UserViewSet)
router.register(r"groups", views.GroupViewSet)
router.register(r"facilities", views.FacilityViewSet)
router.register(r"projects", views.ProjectViewSet)
router.register(r"datasets", views.DatasetViewSet)
router.register(r"templates", views.TemplateViewSet)
router.register(r"metadata", views.FilledTemplateViewSet)

urlpatterns = [
    path("api/v1/", include(router.urls)),
    path("", RedirectView.as_view(url="api/v1", permanent=True)),
    path("admin/", admin.site.urls),
    path("api/auth/", include("rest_framework.urls", namespace="rest_framework")),
    path("oidc/", include("mozilla_django_oidc.urls")),
    path("__debug__/", include("debug_toolbar.urls")),
]
