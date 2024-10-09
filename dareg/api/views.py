from django.contrib.auth.models import User, Group
from requests import Response
from rest_framework import viewsets, permissions
from django_filters.rest_framework import DjangoFilterBackend
from .models import Facility, Project, Dataset, Schema, UserProfile, PermsGroup
from .serializers import (
    UserSerializer,
    GroupSerializer,
    FacilitySerializer,
    ProjectSerializer,
    DatasetSerializer,
    SchemaSerializer,
    ProfileSerializer,
)
from .permissions import NestedPerms, update_perms, SameUser
from guardian.shortcuts import get_objects_for_user
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from onedata_api.middleware import create_new_dataset, create_public_share, establish_dataset, rename_folder

class ProfileViewSet(viewsets.ModelViewSet):
    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated, SameUser]

    def get_queryset(self):
        queryset = UserProfile.objects.all()
        return queryset.filter(user=self.request.user.id)

    def get_object(self):
        queryset = self.get_queryset()
        return queryset.get(user=self.request.user.id)
     

class UserViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to be viewed or edited.
    """

    queryset = User.objects.all().order_by("-date_joined")
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]


class GroupViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows groups to be viewed or edited.
    """

    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    permission_classes = [permissions.IsAuthenticated]


class FacilityViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows facilities to be viewed or edited.
    """

    serializer_class = FacilitySerializer
    permission_classes = [NestedPerms]

    def get_queryset(self):
        
        queryset = Facility.objects.all()
        
        if self.action == 'retrieve':
            return queryset.filter(id=self.kwargs.get('pk'))
        
        elif self.action == 'list':
            return [obj for obj in queryset if obj.perm_atleast(self.request, PermsGroup.VIEWER)]
        
        else:
            return queryset
    

class SchemaViewSet(viewsets.ModelViewSet):
    queryset = Schema.objects.all()
    serializer_class = SchemaSerializer
    permission_classes = []


class ProjectViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows project to be viewed or edited.
    """

    serializer_class = ProjectSerializer
    permission_classes = [NestedPerms]

    def get_queryset(self):
        
        queryset = Project.objects.all()
        
        if self.action == 'retrieve':
            return queryset.filter(id=self.kwargs.get('pk'))
        
        elif self.action == 'list':
            return [obj for obj in queryset if obj.perm_atleast(self.request, PermsGroup.VIEWER)]
        
        else:
            return queryset

    
    def perform_create(self, serializer):
        
        if Facility.objects.get(id=self.request.data.get('facility')).perm_atleast(self.request, PermsGroup.EDITOR):
            serializer.save()
        
        else:
            raise PermissionDenied({"detail": "You do not have permissions to create a new project in this facility."})
        
    def perform_update(self, serializer):
        
        if Project.objects.get(id=self.kwargs.get('pk')).perm_atleast(self.request, PermsGroup.OWNER):
            update_perms(self.kwargs.get('pk'), self.request)
        serializer.save()
    

class DatasetViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows dataset to be viewed or edited.
    """

    serializer_class = DatasetSerializer
    permission_classes = [NestedPerms]

    def get_queryset(self):
        
        if self.request.GET.get('project'):
            queryset = Dataset.objects.filter(project=self.request.GET.get('project'))
        else:
            queryset = Dataset.objects.all()
        
        if self.action == 'retrieve':
            return queryset.filter(id=self.kwargs.get('pk'))
        
        elif self.action == 'list':
            return [obj for obj in queryset if obj.perm_atleast(self.request, PermsGroup.VIEWER)]

        else:
            return queryset
    
    def perform_create(self, serializer):
        
        if Project.objects.get(id=self.request.data.get('project')).perm_atleast(self.request, PermsGroup.EDITOR):
            serializer.save()
        
        else:
            raise PermissionDenied({"detail": "You do not have permissions to create a new dataset in this project."})
    
    def perform_update(self, serializer):
        
        if Dataset.objects.get(id=self.kwargs.get('pk')).perm_atleast(self.request, PermsGroup.OWNER):
            update_perms(self.kwargs.get('pk'), self.request)
        serializer.save()

    def update(self, request, *args, **kwargs):
        serializer = DatasetSerializer(data=request.data)

        old_dataset = Dataset.objects.get(id=self.kwargs.get('pk'))

        if not serializer.is_valid(raise_exception=True):
            return Response(serializer.errors, status=400)

        if old_dataset.name != request.data.get('name'):
            rename_folder(old_dataset.project, old_dataset.onedata_file_id, request.data.get('name'))

        return super().update(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = DatasetSerializer(data=request.data)
        if not serializer.is_valid(raise_exception=True):
            return Response(serializer.errors, status=400)
        
        project = Project.objects.get(id=request.data.get('project'))
        folder, err_folder = create_new_dataset(project, request.data.get('name'))
        if err_folder:
            raise ValueError(err_folder)
        
        request.data["onedata_file_id"] = folder.file_id

        share, err_share = create_public_share(project, request.data.get('name'), request.data.get('description'), folder)
        request.data["onedata_share_id"] = share.share_id

        # Returns dataset id
        datasetId, err_dataset = establish_dataset(project, folder)
        request.data["onedata_dataset_id"] = datasetId
        
        return super().create(request, *args, **kwargs)
    
    @action(detail=False, methods=['post'])
    def create_public_share(self, request, *args, **kwargs):
        if self.kwargs.get('pk') is None:
            raise ValueError("Dataset ID is required to create a public share.")
        dataset = Dataset.objects.get(id=self.kwargs.get('pk'))
        if not dataset.perms_atleast(request, PermsGroup.EDITOR):
            raise PermissionDenied({"detail": "You do not have permissions to create a public share for this dataset."})
        share = create_public_share(dataset)
        dataset.onedata_share_id = share.share_id
        dataset.save()
        return Response({"onedata_share_id": share.share_id})
    
    @action(detail=False, methods=['post'])
    def create_dataset(self, request, *args, **kwargs):
        if self.kwargs.get('pk') is None:
            raise ValueError("Dataset ID is required to create a visit folder.")
        dataset = Dataset.objects.get(id=self.kwargs.get('pk'))
        if not dataset.perms_atleast(request, PermsGroup.EDITOR):
            raise PermissionDenied({"detail": "You do not have permissions to create a visit folder for this dataset."})
        folder = establish_dataset(dataset.project, dataset.onedata_file_id)
        dataset.onedata_visit_id = folder
        dataset.save()
        return Response({"onedata_dataset_id": folder})

    @action(detail=False, methods=['post'])
    def create_onedata_folder(self, request, *args, **kwargs):
        if self.kwargs.get('pk') is None:
            raise ValueError("Dataset ID is required to create a Onedata folder.")
        dataset = Dataset.objects.get(id=self.kwargs.get('pk'))
        if not dataset.perms_atleast(request, PermsGroup.EDITOR):
            raise PermissionDenied({"detail": "You do not have permissions to create a visit folder for this dataset."})
        folder, err_folder = create_new_dataset(dataset.project, request.data.get('name'))
        dataset.onedata_file_id = folder
        dataset.save()
        return Response({"onedata_file_id": folder.file_id})