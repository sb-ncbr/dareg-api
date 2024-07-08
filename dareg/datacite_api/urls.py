from django.contrib import admin
from django.urls import path, include
from .views import DoiViewSet

# router = routers.DefaultRouter()
# router.register(r"files", FilesViewSet.as_view(), basename="files")

urlpatterns = [
    path(r"dois/", DoiViewSet.as_view(), name='doi')
]
