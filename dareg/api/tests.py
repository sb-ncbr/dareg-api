from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth.models import User
from knox.models import AuthToken
from django.utils.timezone import now, timedelta
from api.models import Facility, Project, Dataset, Experiment, Instrument
from unittest.mock import patch, MagicMock
from uuid import uuid4


class ReservationListViewTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.token = AuthToken.objects.create(self.user)[1]
        self.auth_header = f"Token {self.token}"

        self.instrument_mock = MagicMock()
        self.facility_mock = MagicMock()
        self.project_mock = MagicMock()
        self.project_mock.id = "11111111-1111-1111-1111-111111111111"

        self.facility_mock.project_set.first.return_value = self.project_mock
        self.instrument_mock.facility = self.facility_mock

        patcher = patch("django.contrib.auth.models.User.instrument", new_callable=MagicMock)
        self.addCleanup(patcher.stop)
        self.instrument_attr = patcher.start()
        self.instrument_attr.__get__ = lambda *args, **kwargs: self.instrument_mock

    def test_get_reservations_in_range(self):
        date_from = (now() - timedelta(hours=4)).isoformat()
        date_to = (now() + timedelta(hours=2)).isoformat()

        response = self.client.get(
            "/api/v1/reservation/",
            {
                "date_from": date_from,
                "date_to": date_to,
            },
            HTTP_AUTHORIZATION=self.auth_header
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)

        for reservation in response.data:
            from_date = reservation["from_date"]
            to_date = reservation["to_date"]
            self.assertLessEqual(from_date, date_to)
            self.assertGreaterEqual(to_date, date_from)

    def test_get_with_invalid_dates(self):
        response = self.client.get(
            "/api/v1/reservation/",
            {
                "date_from": "not-a-date",
                "date_to": "also-not-a-date",
            },
            HTTP_AUTHORIZATION=self.auth_header
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_requires_authentication(self):
        response = self.client.get("/api/v1/reservation/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class TempTokenAPIViewTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.token = AuthToken.objects.create(self.user)[1]
        self.auth_header = f"Token {self.token}"

        # Create Facility
        self.facility = Facility.objects.create(name="Test Facility", onedata_provider_url="https://provider.url",
                                                created_by=self.user)

        # Create Project
        self.project = Project.objects.create(name="Test Project", facility=self.facility, description="desc",
                                              created_by=self.user)

        # Create Dataset
        self.dataset = Dataset.objects.create(name="Test Dataset", project=self.project, description="desc",
                                              created_by=self.user)

        # Create Experiment
        self.experiment = Experiment.objects.create(
            dataset=self.dataset,
            name="Test Experiment",
            onedata_file_id="test_onedata_file_id",
            created_by=self.user
        )

        self.url = f"/api/v1/temp-token/{self.experiment.id}/"

    @patch("api.views.create_new_temp_token")
    def test_temp_token_success(self, mock_create_token):
        mock_create_token.return_value = ("mocked-token-xyz", None)

        response = self.client.post(
            self.url,
            HTTP_AUTHORIZATION=self.auth_header
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["token"], "mocked-token-xyz")
        self.assertEqual(response.data["provider_url"], self.facility.onedata_provider_url)
        self.assertEqual(response.data["one_data_directory_id"], self.experiment.onedata_file_id)

    def test_requires_authentication(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invalid_experiment_id(self):
        invalid_url = f"/api/v1/temp-token/{uuid4()}/"
        response = self.client.post(
            invalid_url,
            HTTP_AUTHORIZATION=self.auth_header
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class InstrumentViewSetTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.token = AuthToken.objects.create(self.user)[1]
        self.auth_header = f"Token {self.token}"

        # Create a facility
        self.facility = Facility.objects.create(
            name="Test Facility",
            abbreviation="TF",
            email="testing@facility.com",
            web="facility.com",
            logo="logo.png",
            onedata_provider_url="https://provider.url",
            onedata_token="onetoken123",
            created_by=self.user
        )

        # Create an instrument associated with the user
        self.instrument = Instrument.objects.create(
            name="Test Instrument",
            support="Test Support",
            contact="Test Contact",
            method="Test Method",
            default_data_dir="/data",
            facility=self.facility,
            user=self.user,
            created_by=self.user
        )

        # Create a token for the user
        self.token = AuthToken.objects.create(user=self.user)[1]

    def test_instrument_metadata(self):
        # Get the metadata endpoint
        url = "/api/v1/instrument/metadata/"

        # Send a GET request with authorization
        response = self.client.get(url, HTTP_AUTHORIZATION=self.auth_header)

        # Ensure the status code is OK
        self.assertEqual(response.status_code, 200)

        # Ensure that the response contains the correct data
        self.assertEqual(response.data["name"], self.instrument.name)
        self.assertEqual(response.data["support"], self.instrument.support)
        self.assertEqual(response.data["contact"], self.instrument.contact)
        self.assertEqual(response.data["method"], self.instrument.method)
        self.assertEqual(response.data["default_data_dir"], self.instrument.default_data_dir)
        self.assertEqual(response.data["facility"]["name"], self.facility.name)
        self.assertEqual(response.data["facility"]["abbreviation"], self.facility.abbreviation)
        self.assertEqual(response.data["facility"]["email"], self.facility.email)
        self.assertEqual(response.data["facility"]["web"], self.facility.web)
        self.assertEqual(response.data["facility"]["logo"], self.facility.logo)

    def test_instrument_metadata_not_found(self):
        # Create a user with no associated instrument
        another_user = User.objects.create_user(username="anotheruser", password="password")
        another_token = AuthToken.objects.create(user=another_user)[1]

        url = "/api/v1/instruments/metadata/"
        response = self.client.get(url, HTTP_AUTHORIZATION=f"Token {another_token}")

        self.assertEqual(response.status_code, 404)


class MockedFolder:
    file_id = "1234"


class ExperimentViewSetTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.token = AuthToken.objects.create(self.user)[1]
        self.auth_header = f"Token {self.token}"

        self.facility = Facility.objects.create(name="Test Facility", onedata_provider_url="https://provider.url",
                                                created_by=self.user)
        self.project = Project.objects.create(name="Test Project", facility=self.facility, description="desc",
                                              created_by=self.user)
        self.dataset = Dataset.objects.create(name="Test Dataset", project=self.project, description="desc",
                                              created_by=self.user)

        self.url = f"/api/v1/experiments/"

    @patch('api.views.create_new_experiment')  # Mocking external call
    def test_create_experiment(self, mock_create_new_experiment):
        # Mock the folder creation
        mock_create_new_experiment.return_value = (MockedFolder(), None)

        # Prepare valid data for creating an experiment
        data = {
            'dataset': self.dataset.id,
            'name': 'New Experiment',
            'status': "new",
        }

        # Send POST request to create an experiment
        response = self.client.post(self.url, data, format='json', HTTP_AUTHORIZATION=self.auth_header)

        # Ensure the request was successful
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Check if the folder creation was triggered
        mock_create_new_experiment.assert_called_once()

        # Check if the onedata_file_id was set correctly
        experiment = Experiment.objects.last()
        self.assertEqual(experiment.onedata_file_id, '1234')

    @patch('api.views.create_new_experiment')  # Mocking external call
    def test_create_experiment_invalid(self, mock_create_new_experiment):
        # Simulate error during folder creation
        mock_create_new_experiment.return_value = (None, "Error creating folder")

        # Prepare valid data for creating an experiment
        data = {
            'dataset': self.dataset.id,
            'name': 'Invalid Experiment',
            'status': 'NEW',
        }

        # Send POST request to create an experiment
        response = self.client.post(self.url, data, format='json', HTTP_AUTHORIZATION=self.auth_header)

        # Expecting a bad request response due to error during folder creation
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('api.views.rename_entry')  # Mocking the folder renaming
    def test_update_experiment(self, mock_rename_entry):
        # Prepare initial data
        experiment = Experiment.objects.create(
            dataset=self.dataset,
            name="Old Experiment",
            status="new",
            created_by=self.user,
        )

        # Prepare updated data
        data = {
            'name': 'Updated Experiment',  # Changing name
            'status': 'success',
            'dataset': self.dataset.id,
        }

        # Send PUT request to update an experiment
        response = self.client.put(f'{self.url}{experiment.id}/', data, format='json',
                                   HTTP_AUTHORIZATION=self.auth_header)

        # Ensure the request was successful
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Ensure that rename_entry was called due to name change
        mock_rename_entry.assert_called_once_with(experiment.dataset.project, experiment.onedata_file_id,
                                                  'Updated Experiment')

        # Verify the experiment data has been updated
        experiment.refresh_from_db()
        self.assertEqual(experiment.name, 'Updated Experiment')

    def test_update_experiment_invalid(self):
        # Prepare initial data
        experiment = Experiment.objects.create(
            dataset=self.dataset,
            name="Old Experiment",
            status="new",
            created_by=self.user,
        )

        # Prepare invalid data (missing name)
        data = {
            'status': 'success',
        }

        # Send PUT request to update an experiment
        response = self.client.put(f'{self.url}{experiment.id}/', data, format='json',
                                   HTTP_AUTHORIZATION=self.auth_header)

        # Expecting a bad request response due to missing name
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_partial_update_experiment(self):
        # Prepare initial data
        experiment = Experiment.objects.create(
            dataset=self.dataset,
            name="Experiment",
            status="NEW",
            created_by=self.user,
        )

        # Prepare partial update data
        data = {
            'status': 'success',  # Only updating the status
        }

        # Send PATCH request to partially update an experiment
        response = self.client.patch(f'{self.url}{experiment.id}/', data, format='json',
                                     HTTP_AUTHORIZATION=self.auth_header)

        # Ensure the request was successful
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify the experiment data has been partially updated
        experiment.refresh_from_db()
        self.assertEqual(experiment.status, 'success')

    def test_partial_update_experiment_invalid(self):
        experiment = Experiment.objects.create(
            dataset=self.dataset,
            name="Experiment",
            status="NEW",
            created_by=self.user,
        )
        data = {
            'status': 'randomStatus',
        }

        response = self.client.patch(f'{self.url}{experiment.id}/', data, format='json',
                                     HTTP_AUTHORIZATION=self.auth_header)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
