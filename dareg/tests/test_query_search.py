from unittest.mock import patch
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from api.models import Facility, Project, Dataset, Schema
from django.contrib.auth.models import User


class MockFolder:
    file_id = "mock-folder-id"

class MockShare:
    share_id = "mock-share-id"

class MockDatasetId:
    pass


def fake_create_new_dataset(project, name):
    return MockFolder(), None

def fake_create_public_share(project, name, description, folder):
    return MockShare(), None

def fake_establish_dataset(project, folder):
    return "mock-dataset-id", None


class QuerySearchTests(APITestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create(username='searchuser', password='a')
        self.client.force_authenticate(user=self.user)

        fac_url = reverse('facility-list')
        response = self.client.post(fac_url, {"name": "Search Fac", "abbreviation": "SF"}, format='json')
        self.fac_id = response.data["id"]

        schema_url = reverse('schema-list')
        schema_data = {
            "name": "Search Schema",
            "description": "Schema for search tests",
            "schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "nested": {
                        "type": "object",
                        "properties": {
                            "author_name": {"type": "string"}
                        }
                    }
                }
            },
            "uischema": {}
        }
        response = self.client.post(schema_url, schema_data, format='json')
        self.schema_id = response.data["id"]

        proj_url = reverse('project-list')
        response = self.client.post(proj_url, {
            "name": "Search Proj",
            "description": "Project for search tests",
            "facility": self.fac_id,
            "default_dataset_schema": self.schema_id
        }, format='json')
        self.proj_id = response.data["id"]

        with patch('api.views.views.create_new_dataset', side_effect=fake_create_new_dataset), \
             patch('api.views.views.create_public_share', side_effect=fake_create_public_share), \
             patch('api.views.views.establish_dataset', side_effect=fake_establish_dataset):

            ds_url = reverse('dataset-list')
            self.client.post(ds_url, {
                "name": "Temperature Dataset",
                "description": "Weather temperature data recorded in lab",
                "project": self.proj_id,
                "schema": self.schema_id,
                "metadata": {
                    "title": "Temperature Study",
                    "nested": {
                        "author_name": "John Doe"
                    }
                }
            }, format='json')

            self.client.post(ds_url, {
                "name": "Pressure Dataset",
                "description": "Atmospheric pressure readings",
                "project": self.proj_id,
                "schema": self.schema_id,
                "metadata": {
                    "title": "Pressure Analysis",
                    "nested": {
                        "author_name": "Jane Smith"
                    }
                }
            }, format='json')

    def test_query_filters_with_and_metadata(self):
        """Query with $and over metadata fields returns correct hits."""
        url = reverse('query-list')
        payload = {
            "model": "Dataset",
            "schema": self.schema_id,
            "filters": {
                "$and": [
                    {"metadata.title": {"$eq": "Temperature Study"}}
                ]
            }
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["text"], "Temperature Dataset")
        highlights = response.data["results"][0]["highlights"]
        self.assertIn("metadata.title", highlights)
        self.assertEqual(highlights["metadata.title"], "Temperature Study")

    def test_query_contains_on_nested_metadata(self):
        """$contains on a nested metadata path uses native JSON search."""
        url = reverse('query-list')
        response = self.client.post(url, {
            "model": "Dataset",
            "schema": self.schema_id,
            "filters": {
                "metadata.nested.author_name": {"$contains": "Doe"}
            }
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["text"], "Temperature Dataset")

    def test_query_free_text_with_schema_metadata(self):
        """Free-text q searches schema string metadata paths via trigram."""
        url = reverse('query-list')
        response = self.client.post(url, {
            "model": "Dataset",
            "schema": self.schema_id,
            "q": "Study"
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        found = False
        for result in response.data["results"]:
            hl = result.get("highlights", {})
            if "metadata.title" in hl and "Study" in str(hl["metadata.title"]):
                found = True
                break
        self.assertTrue(found, "Expected metadata title to appear in highlights for q=Study")

    def test_query_highlights_return_dict(self):
        """Highlights are a dict, not a list of strings."""
        url = reverse('query-list')
        response = self.client.post(url, {
            "model": "Dataset",
            "schema": self.schema_id,
            "filters": {
                "metadata.title": {"$eq": "Temperature Study"}
            }
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        highlights = response.data["results"][0]["highlights"]
        self.assertIsInstance(highlights, dict)
