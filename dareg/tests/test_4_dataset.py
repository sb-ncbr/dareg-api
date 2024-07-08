from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from api.models import Facility
from django.contrib.auth.models import User

class DatasetTests(APITestCase):

    def setUp(self):
        self.client = APIClient()
        self.user1 = User.objects.create(username='user1', password='a')
        self.user2 = User.objects.create(username='user2', password='b')
        self.client.force_authenticate(user=self.user1)

        url = reverse('facility-list')
        data = {"name":'Test Fac 1', "abbreviation":'Fac Abb 1'}
        response = self.client.post(url, data, format='json')

        self.fac_id = response.data["id"]

        url = reverse('schema-list')
        data = {"name":'Test Schema 1',
                "description":'Schema descr 1',
                "schema": {"hello": "world"},
                "uischema": {"hello2": "world2"}
                }
        response = self.client.post(url, data, format='json')

        self.schema_id = response.data["id"]

        url = reverse('project-list')
        data = {"name":'Test Proj 1',
                "description":'Proj descr 1',
                "facility": self.fac_id,
                "default_dataset_schema": self.schema_id
                }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.proj_id = response.data["id"]

        url = reverse('dataset-list')
        data = {"name":'Test Dataset 1',
                "description":'Dataset descr 1',
                "project": self.proj_id,
                "schema": self.schema_id,
                "metadata": {"meta": "meta1"}
                }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.dataset_id = response.data["id"]


    def test_make_dataset(self):

        url = reverse('dataset-list')
        data = {"name":'Test Dataset 2',
                "description":'Dataset descr 2',
                "project": self.proj_id,
                "schema": self.schema_id,
                "metadata": {"meta": "meta2"}
                }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.get(url)
        self.assertEqual(len(response.data['results']), 2)
        self.assertEqual(response.data['results'][0]['name'], 'Test Dataset 1')
        self.assertEqual(response.data['results'][1]['name'], 'Test Dataset 2')


    def test_dataset_mod(self):
        
        updated_data = {
            "name": "Mod Dataset 1"
        }

        url = reverse('dataset-detail', args=[self.dataset_id])
        response = self.client.patch(url, updated_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        url = reverse('dataset-detail', args=[self.dataset_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Mod Dataset 1')
    

    def test_dataset_perms(self):
        
        self.client.force_authenticate(user=self.user2)

        url = reverse('dataset-detail', args=[self.dataset_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.user1)

        url = reverse('dataset-detail', args=[self.dataset_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


        updated_data = {'shares': response.data['shares'] + [{'id': self.user2.pk, 'perms': 'viewer'}]}
        url = reverse('project-detail', args=[self.proj_id])
        response = self.client.patch(url, updated_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=self.user2)

        url = reverse('dataset-detail', args=[self.dataset_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data['perms'], 'viewer')

