from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from api.models import Facility
from django.contrib.auth.models import User

class ProjectTests(APITestCase):

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



    def test_make_proj(self):

        url = reverse('project-list')
        data = {"name":'Test Proj 2',
                "description":'Proj descr 2',
                "facility": self.fac_id,
                "default_dataset_schema": self.schema_id
                }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.get(url)
        self.assertEqual(len(response.data['results']), 2)
        self.assertEqual(response.data['results'][0]['name'], 'Test Proj 1')
        self.assertEqual(response.data['results'][1]['name'], 'Test Proj 2')


    def test_proj_mod(self):
        
        updated_data = {
            "name": "Mod Proj 1"
        }

        url = reverse('project-detail', args=[self.proj_id])
        response = self.client.patch(url, updated_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        url = reverse('project-detail', args=[self.proj_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Mod Proj 1')
    

    def test_proj_perms(self):

        self.client.force_authenticate(user=self.user2)

        url = reverse('project-detail', args=[self.proj_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        url = reverse('facility-list')
        data = {"name":'Test Fac 2', "abbreviation":'Fac Abb 2'}
        response = self.client.post(url, data, format='json')
        self.fac2_id = response.data["id"]

        url = reverse('project-list')
        data = {"name":'Test Proj 2',
                "description":'Proj descr 2',
                "facility": self.fac2_id,
                "default_dataset_schema": self.schema_id
                }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertEqual(response.data['perms'], 'owner')
        self.assertEqual(len(response.data['shares']), 1)
        self.assertEqual(response.data['shares'][0]['id'], self.user2.pk)
        self.assertEqual(response.data['shares'][0]['perms'], "owner")

        proj2_id = response.data["id"]

        updated_data = {'shares': response.data['shares'] + [{'id': self.user1.pk, 'perms': 'editor'}]}
        url = reverse('project-detail', args=[proj2_id])
        response = self.client.patch(url, updated_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data['perms'], 'owner')
        self.assertEqual(len(response.data['shares']), 2)
        self.assertEqual(response.data['shares'][1]['id'], self.user1.pk)
        self.assertEqual(response.data['shares'][1]['perms'], "editor")

        self.client.force_authenticate(user=self.user1)

        url = reverse('project-detail', args=[proj2_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

