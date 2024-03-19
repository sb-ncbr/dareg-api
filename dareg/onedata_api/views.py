from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
import oneprovider_client
from onedata_wrapper.api.file_operations_api import FileOperationsApi
from onedata_wrapper.models.filesystem.dir_entry import DirEntry
from onedata_wrapper.models.space.space_request import SpaceRequest
from onedata_wrapper.selectors.file_attribute import ALL as FA_ALL
from api.models import Project, Dataset

class FilesViewSet(APIView):

    permission_classes = (permissions.IsAuthenticatedOrReadOnly,)

    oneprovider_configuration = oneprovider_client.configuration.Configuration()

    def get(self, request):

        if request.GET.get('dataset_id') is None:
            return Response({"error": "dataset_id is a required parameter"})

        dataset = Dataset.objects.get(id=request.GET.get('dataset_id'))
        space_id = ""
        if request.GET.get('file_id') is None:
            space_id = dataset.project.onedata_space_id
        else:
            space_id = request.GET.get('file_id')

        facility_token = dataset.project.facility.onedata_token
        if space_id is None or facility_token is None or space_id == "" or facility_token == "":
            return Response({"error": "Dataset doesn't have any supported space. Please contact the administrator of DAREG."})

        self.oneprovider_configuration.host = dataset.project.facility.onedata_provider_url
        self.oneprovider_configuration.api_key['X-Auth-Token'] = facility_token

        print("XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX", self.oneprovider_configuration.host, self.oneprovider_configuration.api_key['X-Auth-Token'], space_id)

        file_op_api = FileOperationsApi(self.oneprovider_configuration)

        # creating SpaceRequest object used for Space retrieval (not using API calls yet)
        space_request = SpaceRequest(space_id=space_id)

        # requesting Space information from Onedata
        space = file_op_api.get_space(space_request)

        # print(space.space_id, space.name)  # space info can be seen here
        # requesting information about Space root file
        file_op_api.get_root(space)

        # treating space root directory as usual directory
        basic_dir = space.root_dir
        # requesting children for actual directory from Onedata
        file_op_api.get_children(basic_dir, FA_ALL)

        
        return Response({"files": basic_dir})
