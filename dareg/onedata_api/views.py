from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
import oneprovider_client
from onedata_wrapper.api.file_operations_api import FileOperationsApi
from onedata_wrapper.models.filesystem.dir_entry import DirEntry
from onedata_wrapper.models.filesystem.file_entry import FileEntry
from onedata_wrapper.models.space.space_request import SpaceRequest
from onedata_wrapper.models.filesystem.entry_request import EntryRequest
from onedata_wrapper.models.filesystem.new_directory_request import NewDirectoryRequest
from onedata_wrapper.selectors.file_attribute import ALL as FA_ALL
from api.models import Project, Dataset
from onedata_api.middleware import create_new_dataset

class SpacesViewSet(APIView):
    
        permission_classes = (permissions.IsAuthenticatedOrReadOnly,)
    
        oneprovider_configuration = oneprovider_client.configuration.Configuration()
    
        def get(self, request):
    
            if request.GET.get('dataset_id') is None:
                return Response({"error": "dataset_id is a required parameter"})
    
            dataset = Dataset.objects.get(id=request.GET.get('dataset_id'))
    
            facility_token = dataset.project.facility.onedata_token
            if facility_token is None or facility_token == "":
                return Response({"error": "Dataset doesn't have any supported space. Please contact the administrator of DAREG."})
    
            self.oneprovider_configuration.host = dataset.project.facility.onedata_provider_url
            self.oneprovider_configuration.api_key['X-Auth-Token'] = facility_token
    
            file_op_api = FileOperationsApi(self.oneprovider_configuration)
    
            # requesting list of spaces from Onedata
            spaces = file_op_api.get_spaces()
    
            return Response({"spaces": spaces})

class FilesViewSet(APIView):

    permission_classes = (permissions.IsAuthenticatedOrReadOnly,)

    oneprovider_configuration = oneprovider_client.configuration.Configuration()
    file_op_api = FileOperationsApi(oneprovider_configuration)

    def post(self, request):
        # return Response(request.data)
        if request.data.get('collection_id') is None:
            return Response({"error": "collection_id is a required parameter"}, status=400)
        if request.data.get('dataset_name') is None:
            return Response({"error": "dataset_name is a required parameter"}, status=400)

        response, share = create_new_dataset(request.data.get('collection_id'), request.data.get('dataset_name'))

        return Response({"files": dict(response), "share": share})

    def get(self, request):

        if request.GET.get('dataset_id') is None:
            return Response({"error": "dataset_id is a required parameter"}, status=400)

        dataset = Dataset.objects.get(id=request.GET.get('dataset_id'))
        space_id = ""
        file_id = ""
        if request.GET.get('file_id') is not None and request.GET.get('file_id') != "" and request.GET.get('file_id') != "null":
            file_id = request.GET.get('file_id')
        else:
            file_id = dataset.onedata_file_id

        if file_id is None or file_id == "":
            return Response({"error": "Dataset is not supported by any Onedata space. Please contact the administrator of DAREG."}, status=404)

        facility_token = dataset.project.facility.onedata_token
        if facility_token is None or facility_token == "":
            return Response({"error": "Facility is not supported by any Onedata space. Please contact the administrator of DAREG."}, status=404)

        self.oneprovider_configuration.host = dataset.project.facility.onedata_provider_url
        self.oneprovider_configuration.api_key['X-Auth-Token'] = facility_token


        # creating SpaceRequest object used for Space retrieval (not using API calls yet)
        file_request = EntryRequest(file_id=file_id)

        # requesting Space information from Onedata
        file = self.file_op_api.get_file(file_request, FA_ALL)

        # requesting children for actual directory from Onedata
        files = self.file_op_api.get_children(file, FA_ALL)

        
        return Response({"files": files})
