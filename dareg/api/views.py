from django.contrib.auth.models import User, Group
from rest_framework import viewsets, permissions
from django_filters.rest_framework import DjangoFilterBackend
from .models import Facility, Project, Dataset, Schema, UserProfile
from .serializers import (
    UserSerializer,
    GroupSerializer,
    FacilitySerializer,
    ProjectSerializer,
    DatasetSerializer,
    SchemaSerializer,
    ProfileSerializer,
)
from .permissions import NestedPerms, max_perm, update_perms
from guardian.shortcuts import get_objects_for_user
from rest_framework.exceptions import PermissionDenied

class ProfileViewSet(viewsets.ModelViewSet):
    serializer_class = ProfileSerializer
    
    def get_queryset(self):
        queryset = UserProfile.objects.all()
        return queryset.filter(user=self.request.user.id)        


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
            return [obj for obj in queryset if max_perm(obj, self.request) >= 1]
        
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
            return [obj for obj in queryset if max_perm(obj, self.request) >= 1]
        
        else:
            return queryset

    
    def perform_create(self, serializer):
        
        if max_perm(Facility.objects.get(id=self.request.data.get('facility')), request=self.request) >= 2:
            serializer.save()
        
        else:
            raise PermissionDenied({"detail": "You do not have permissions to create a new project in this facility."})
        
    def perform_update(self, serializer):
        
        if max_perm(Project.objects.get(id=self.kwargs.get('pk')), request=self.request) >= 3:
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
            return [obj for obj in queryset if max_perm(obj, self.request) >= 1]

        else:
            return queryset
    
    def perform_create(self, serializer):
        
        if max_perm(Project.objects.get(id=self.request.data.get('project')), request=self.request) >= 2:
            serializer.save()
        
        else:
            raise PermissionDenied({"detail": "You do not have permissions to create a new dataset in this project."})
    
    def perform_update(self, serializer):
        
        if max_perm(Dataset.objects.get(id=self.kwargs.get('pk')), request=self.request) >= 3:
            update_perms(self.kwargs.get('pk'), self.request)
        serializer.save()

