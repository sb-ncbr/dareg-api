import requests
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from api.models import Dataset, PermsGroup
from rest_framework.views import APIView
from rest_framework import permissions
from api.permissions import NestedPerms
from decouple import config
from datacite_api.backends import build_datacite_request

DATACITE_API_URL = config('DATACITE_API_URL')
DATACITE_API_USERNAME = config('DATACITE_API_USERNAME')
DATACITE_API_PASSWORD = config('DATACITE_API_PASSWORD')

headers = {
    'Content-Type': 'application/vnd.api+json',
}
auth = (DATACITE_API_USERNAME, DATACITE_API_PASSWORD)


class DoiViewSet(APIView):

    permission_classes = []

    def get(self, request):

        current_dataset = get_object_or_404(Dataset, pk=request.GET.get('dataset_id'))

        if current_dataset.perm_atleast(request, PermsGroup.VIEWER):

            if current_dataset.doi:
                response = requests.get(f"{DATACITE_API_URL}/{current_dataset.doi}", headers=headers, auth=auth)
                return JsonResponse(response.json()['data'])

            else:
                return JsonResponse({
                    "id": "",
                    "attributes": {
                        "state": "none"
                    }
                })
        
        else:
            return HttpResponse('', status=401, content_type='text/html')
        

    def post(self, request):

        current_dataset = get_object_or_404(Dataset, pk=request.data.get('dataset_id'))

        if current_dataset.perm_atleast(request, PermsGroup.EDITOR):

            metadata = build_datacite_request(current_dataset)

            response = requests.post(DATACITE_API_URL, json=metadata, headers=headers, auth=auth)
            
            if response.status_code == 201:
                current_dataset.doi = response.json()['data']['id']
                current_dataset.save()

            return JsonResponse({
                "success": response.status_code == 201,
                "dataset_id": current_dataset.id,
            })
        
        else:
            return HttpResponse('', status=401, content_type='text/html')
    
    def put(self, request):

        current_dataset = get_object_or_404(Dataset, pk=request.data.get('dataset_id'))

        if current_dataset.perm_atleast(request, PermsGroup.EDITOR):

            metadata = build_datacite_request(current_dataset)

            response = requests.put(f"{DATACITE_API_URL}/{current_dataset.doi}/", json=metadata, headers=headers, auth=auth)

            return JsonResponse({
                "success": response.status_code == 200,
                "dataset_id": current_dataset.id,
            })

        else:
            return HttpResponse('', status=401, content_type='text/html')
        
    def delete(self, request):

        current_dataset = get_object_or_404(Dataset, pk=request.data.get('dataset_id'))

        if current_dataset.perm_atleast(request, PermsGroup.EDITOR):

            response = requests.delete(f"{DATACITE_API_URL}/{current_dataset.doi}/", headers=headers, auth=auth)

            return JsonResponse({
                "success": response.status_code == 200,
                "dataset_id": current_dataset.id,
            })

        else:
            return HttpResponse('', status=401, content_type='text/html')
