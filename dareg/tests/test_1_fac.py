from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from api.models import Facility
from django.contrib.auth.models import User

class FacilityTests(APITestCase):

    def setUp(self):
        self.client = APIClient()
        self.user1 = User.objects.create(username='user1', password='a')
        self.user2 = User.objects.create(username='user2', password='b')
        self.client.force_authenticate(user=self.user1)

        url = reverse('facility-list')
        data = {"name":'Test Fac 1', "abbreviation":'Fac Abb 1'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.fac_id = response.data["id"]


    def test_make_fac(self):

        url = reverse('facility-list')
        data = {"name":'Test Fac 2', "abbreviation":'Fac Abb 2'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.get(url)
        self.assertEqual(len(response.data['results']), 2)
        self.assertEqual(response.data['results'][0]['name'], 'Test Fac 1')
        self.assertEqual(response.data['results'][1]['name'], 'Test Fac 2')


    def test_fac_mod(self):
        
        updated_data = {
            "name": "Mod Fac 1"
        }

        url = reverse('facility-detail', args=[self.fac_id])
        response = self.client.patch(url, updated_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        url = reverse('facility-detail', args=[self.fac_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Mod Fac 1')
    

    def test_fac_perms(self):

        self.client.force_authenticate(user=self.user2)

        url = reverse('facility-detail', args=[self.fac_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        url = reverse('facility-list')
        data = {"name":'Test Fac 2', "abbreviation":'Fac Abb 2'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertEqual(response.data['perms'], 'owner')
        self.assertEqual(len(response.data['shares']), 1)
        self.assertEqual(response.data['shares'][0]['id'], self.user2.pk)
        self.assertEqual(response.data['shares'][0]['perms'], "owner")
