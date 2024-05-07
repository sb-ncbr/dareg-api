from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from rest_framework import routers
from onedata_api.views import FilesViewSet

# router = routers.DefaultRouter()
# router.register(r"files", FilesViewSet.as_view(), basename="files")

urlpatterns = [
    path(r"files/", FilesViewSet.as_view(), name='files')
]