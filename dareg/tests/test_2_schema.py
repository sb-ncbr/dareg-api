from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from api.models import Facility
from django.contrib.auth.models import User

class SchemaTests(APITestCase):

    def setUp(self):
        self.client = APIClient()
        self.user1 = User.objects.create(username='user1', password='a')
        self.user2 = User.objects.create(username='user2', password='b')
        self.client.force_authenticate(user=self.user1)

        url = reverse('schema-list')
        data = {"name":'Test Schema 1',
                "description":'Schema descr 1',
                "schema": {"hello": "world"},
                "uischema": {"hello2": "world2"}
                }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.schema_id = response.data["id"]


    def test_make_schema(self):

        url = reverse('schema-list')
        data = {"name":'Test Schema 2',
                "description":'Schema descr 2',
                "schema": {"schema2": "s2"},
                "uischema": {"uischema2": "ui2"}
                }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.get(url)
        self.assertEqual(len(response.data['results']), 2)
        self.assertEqual(response.data['results'][0]['name'], 'Test Schema 1')
        self.assertEqual(response.data['results'][1]['name'], 'Test Schema 2')


    def test_schema_mod(self):
        
        updated_data = {
            "schema": {"new schema": "wow"}
        }

        url = reverse('schema-detail', args=[self.schema_id])
        response = self.client.patch(url, updated_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        url = reverse('schema-detail', args=[self.schema_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['schema'], {"new schema": "wow"})
    
