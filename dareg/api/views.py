import uuid
from datetime import datetime, timedelta, timezone
from importlib.metadata import metadata

import oneprovider_client
import requests
from django.contrib.auth.models import User, Group
from django.http import HttpResponse
from onedata_wrapper.api.file_operations_api import FileOperationsApi
from onedata_wrapper.models.filesystem.entry_request import EntryRequest
from onedata_wrapper.selectors.file_attribute import ALL as FA_ALL
from rest_framework import permissions, status
from rest_framework.authentication import TokenAuthentication
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser, FileUploadParser
from rest_framework.views import APIView

from .models import Facility, Project, Dataset, Schema, UserProfile, PermsGroup, Instrument, Experiment
from .serializers import (
    UserSerializer,
    GroupSerializer,
    FacilitySerializer,
    ProjectSerializer,
    DatasetSerializer,
    SchemaSerializer,
    ProfileSerializer,
    ReservationSerializer,
    InstrumentSerializer, ExperimentSerializer, DatasetResponseSerializer, TempTokenSerializer,
    ProjectResponseSerializer
)
from .permissions import NestedPerms, update_perms, SameUser
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse

from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import action

from onedata_api.middleware import create_new_dataset, create_public_share, establish_dataset, rename_entry, \
    create_new_experiment, create_new_temp_token, get_file_metadata


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

@extend_schema(
    responses=ProjectResponseSerializer
)
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
    
@extend_schema(
    request=DatasetSerializer,
    responses=DatasetResponseSerializer
)
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
            rename_entry(old_dataset.project, old_dataset.onedata_file_id, request.data.get('name'))

        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
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

    @action(detail=True, methods=['get'])
    def get_by_reservation_id(self, request, *args, **kwargs):
        if self.kwargs.get('pk') is None:
            return Response({"error": "Dataset ID is required to create a Onedata folder."},
                            status=status.HTTP_400_BAD_REQUEST)

        dataset = get_object_or_404(Dataset, reservationId=self.kwargs.get('pk'))
        serializer = self.get_serializer(dataset, many=False)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def shadow(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid(raise_exception=True):
            return Response(serializer.errors, status=400)

        project = Project.objects.get(id=request.data.get('project'))

        metadata, error = get_file_metadata(project, request.data.get("onedata_file_id"))

        return super().create(request, *args, **kwargs)


class ExperimentViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows experiments to be viewed or edited.
    """
    queryset = Experiment.objects.all()
    serializer_class = ExperimentSerializer
    permission_classes = [NestedPerms, IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = ExperimentSerializer(data=request.data)
        if not serializer.is_valid(raise_exception=True):
            return Response(serializer.errors, status=400)

        dataset = Dataset.objects.get(id=request.data.get('dataset'))
        folder, err_folder = create_new_experiment(dataset, str(uuid.uuid4()))
        if err_folder:
            raise ValueError(err_folder)

        request.data["onedata_file_id"] = folder.file_id

        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        serializer = ExperimentSerializer(data=request.data)

        old_experiment = Experiment.objects.get(id=self.kwargs.get('pk'))

        if not serializer.is_valid(raise_exception=True):
            return Response(serializer.errors, status=400)

        if old_experiment.name != request.data.get('name'):
            rename_entry(old_experiment.dataset.project, old_experiment.onedata_file_id, request.data.get('name'))

        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return super().update(request, *args, **kwargs)


class InstrumentViewSet(viewsets.ModelViewSet):
    queryset = Instrument.objects.all()
    serializer_class = InstrumentSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def metadata(self, request, *args, **kwargs):
        serializer = self.get_serializer_class()
        try:
            instrument = Instrument.objects.get(id=request.user.instrument.id)
            data = serializer(instrument).data
            return Response(data)
        except Instrument.DoesNotExist:
            return Response("Instrument not found", status=status.HTTP_404_NOT_FOUND)


class ReservationListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='date_from', description='ISO formated FROM timestamp', required=True, type=str),
            OpenApiParameter(name='date_to', description='ISO formated TO timestamp', required=True, type=str),
        ],
        responses={
            200: OpenApiResponse(response=ReservationSerializer(many=True), description='Created. New resource in response'),
        }
    )
    def get(self, request, *args, **kwargs):
        date_from = request.query_params.get("date_from") or datetime.now(timezone.utc).isoformat()
        date_to = request.query_params.get("date_to") or (datetime.now(timezone.utc) + timedelta(days=1)).isoforxmat()
        project = request.user.instrument.facility.project_set.first()

        reservations = [
            {
                "id": "b171517a-a79a-4170-bef5-ffe93519ba92",
                "name": "Reservation 1",
                "from_date": (datetime.now(timezone.utc) + timedelta(hours=-5)).isoformat(),
                "to_date": (datetime.now(timezone.utc) + timedelta(hours=-3)).isoformat(),
                "user": "David Konečný",
                "description": "This is a test reservation",
            },
            {
                "id": "cee6d34b-991d-4691-b7da-c65f1fa17492",
                "name": "Reservation 2",
                "from_date": (datetime.now(timezone.utc) + timedelta(hours=-1)).isoformat(),
                "to_date": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                "user": "David Konečný",
                "description": "This is a test reservation",
            },
            {
                "id": "1cb2a4dd-702c-4d92-a360-d649a230dc37",
                "name": "Reservation 3",
                "from_date": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
                "to_date": (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat(),
                "user": "David Konečný",
                "description": "This is a test reservation",
            }
        ]

        for reservation in reservations:
            reservation["project_id"] = str(project.id)

        try:
            date_from_parsed = datetime.fromisoformat(date_from)
            date_to_parsed = datetime.fromisoformat(date_to)

            reservations = [
                event for event in reservations
                if datetime.fromisoformat(event["from_date"]) <= date_to_parsed and date_from_parsed <= datetime.fromisoformat(event["to_date"])
            ]

            # Serialize the filtered data
            serializer = ReservationSerializer(data=reservations, many=True)
            if serializer.is_valid():
                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except ValueError as e:
            return Response({"error": "Invalid date format", "details": str(e)},
                            status=status.HTTP_400_BAD_REQUEST)


class ReservationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={
            200: OpenApiResponse(response=ReservationSerializer(), description='Reservation details'),
            404: OpenApiResponse(description='Reservation not found')
        }
    )
    def get(self, request, id, *args, **kwargs):
        reservations = [
            {
                "id": "b171517a-a79a-4170-bef5-ffe93519ba92",
                "name": "Reservation 1",
                "from_date": (datetime.now(timezone.utc) + timedelta(hours=-5)).isoformat(),
                "to_date": (datetime.now(timezone.utc) + timedelta(hours=-3)).isoformat(),
                "user": "David Konečný",
                "description": "This is a test reservation",
            },
            {
                "id": "cee6d34b-991d-4691-b7da-c65f1fa17492",
                "name": "Reservation 2",
                "from_date": (datetime.now(timezone.utc) + timedelta(hours=-1)).isoformat(),
                "to_date": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                "user": "David Konečný",
                "description": "This is a test reservation",
            },
            {
                "id": "1cb2a4dd-702c-4d92-a360-d649a230dc37",
                "name": "Reservation 3",
                "from_date": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
                "to_date": (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat(),
                "user": "David Konečný",
                "description": "This is a test reservation",
            }
        ]

        try:
            reservation = next((reservation for reservation in reservations if reservation.get("id") == str(id)), None)
            project = request.user.instrument.facility.project_set.first()
            reservation["project_id"] = str(project.id)
            if reservation:
                return Response(reservation, status=status.HTTP_200_OK)
            return Response({"error": "Reservation not found"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError:
            return Response({"error": "Invalid reservation ID format"}, status=status.HTTP_400_BAD_REQUEST)

class TempTokenAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, id: str, *args, **kwargs):
        experiment = get_object_or_404(Experiment, id=id)
        dataset = experiment.dataset
        project = dataset.project
        facility = project.facility

        token, error = create_new_temp_token(facility, project, dataset)

        # Serialize the filtered data
        data = {
            "token": token,
            "provider_url": facility.onedata_provider_url,
            "one_data_directory_id": experiment.onedata_file_id
        }
        serializer = TempTokenSerializer(data=data)
        if serializer.is_valid():
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)