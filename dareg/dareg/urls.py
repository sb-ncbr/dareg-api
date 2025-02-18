from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from rest_framework import routers
from api import views
from onedata_api.urls import urlpatterns as onedata_router
from datacite_api.urls import urlpatterns as datacite_router
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from uuid import UUID

router = routers.DefaultRouter()
router.register(r"users", views.UserViewSet)
router.register(r"groups", views.GroupViewSet)
router.register(r"facilities", views.FacilityViewSet, basename='facility')
router.register(r"projects", views.ProjectViewSet, basename='project')
router.register(r"datasets", views.DatasetViewSet, basename='dataset')
router.register(r"schemas", views.SchemaViewSet)
router.register(r"profile", views.ProfileViewSet, basename='profile')
router.register(r"instrument", views.InstrumentViewSet, basename='instrument')
router.register(r"experiments", views.ExperimentViewSet, basename='experiment')

urlpatterns = [
    path("api/v1/", include(router.urls)),
    path("onedata-api/v1/", include(onedata_router)),
    path("datacite-api/v1/", include(datacite_router)),
    path("", RedirectView.as_view(url="api/v1", permanent=True)),
    path("admin/", admin.site.urls),
    path("api/auth/", include("rest_framework.urls", namespace="rest_framework")),
    path("oidc/", include("mozilla_django_oidc.urls")),
    path("__debug__/", include("debug_toolbar.urls")),
    path("api/v1/reservation/", views.ReservationListView.as_view(), name="reservation"),
    path("api/v1/temp-token/<uuid:id>/", views.TempTokenAPIView.as_view(), name="temp-token"),
    path("api/token/", include("knox.urls")),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]
