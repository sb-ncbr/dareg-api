from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth.models import User
from urllib.parse import urlencode

class DataciteTests(APITestCase):

    def setUp(self):
        self.client = APIClient()
        self.user1 = User.objects.create(username='user1', password='a')
        self.user2 = User.objects.create(username='user2', password='b')
        self.client.force_authenticate(user=self.user1)

        ## make a facility

        url = reverse('facility-list')
        data = {"name":'Test Fac 1', "abbreviation":'Fac Abb 1'}
        response = self.client.post(url, data, format='json')

        self.fac_id = response.data["id"]

        ## make a schema

        url = reverse('schema-list')
        data = {"name":'Test Schema 1',
                "description":'Schema descr 1',
                "schema": {"hello": "world"},
                "uischema": {"hello2": "world2"}
                }
        response = self.client.post(url, data, format='json')

        self.schema_id = response.data["id"]

        ## make a project

        url = reverse('project-list')
        data = {"name":'Test Proj 1',
                "description":'Proj descr 1',
                "facility": self.fac_id,
                "default_dataset_schema": self.schema_id
                }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.proj_id = response.data["id"]

        ## make a dataset

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


    def test_no_doi(self):

        url = reverse('doi') + '?' + urlencode({'dataset_id': self.dataset_id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['attributes']['state'], 'none')


    def test_get_doi(self):

        ## get a new doi

        url = reverse('doi')
        data = { "dataset_id": self.dataset_id }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['success'], True)
        self.assertEqual(response.json()['dataset_id'], self.dataset_id)
        
        ## check if doi exists

        url = reverse('doi') + '?' + urlencode({'dataset_id': self.dataset_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['attributes']['state'], 'draft')
        self.assertEqual(response.json()['type'], 'dois')

        ## delete doi

        url = reverse('doi')
        data = { "dataset_id": self.dataset_id }
        response = self.client.delete(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    

    def test_doi_perms(self):

        ## login as user2
        
        self.client.force_authenticate(user=self.user2)

        ## user2 does not have access to Test Dataset 1

        url = reverse('doi') + '?' + urlencode({'dataset_id': self.dataset_id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        ## login as user1

        self.client.force_authenticate(user=self.user1)

        ## give editor perms to user2

        url = reverse('dataset-detail', args=[self.dataset_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        updated_data = {'shares': response.data['shares'] + [{'id': self.user2.pk, 'perms': 'editor'}]}
        url = reverse('dataset-detail', args=[self.dataset_id])
        response = self.client.patch(url, updated_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        ## login as user2

        self.client.force_authenticate(user=self.user2)

        url = reverse('doi') + '?' + urlencode({'dataset_id': self.dataset_id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

