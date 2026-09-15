import json
from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone
from api.models import (
    Facility, Project, Dataset, Experiment, Schema,
    WorkflowTemplate, WorkflowType, WorkflowParams,
    Job, JobStatus, JobLogLevel, JobParams,
    validate_app_config_value
)


class WorkflowTemplateModelTest(TestCase):
    """Test suite for WorkflowTemplate model"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.facility = Facility.objects.create(
            name='Test Facility',
            abbreviation='TF',
            created_by=self.user,
            modified_by=self.user,
            onedata_provider_url='https://oneprovider.test.com/api/v3/oneprovider',
            onedata_token='test_token_123'
        )
        self.project = Project.objects.create(
            facility=self.facility,
            name='Test Project',
            description='Test Description',
            created_by=self.user,
            modified_by=self.user,
            onedata_space_id='space123'
        )

    def test_workflow_template_creation(self):
        """Test basic workflow template creation"""
        workflow = WorkflowTemplate.objects.create(
            onedata_workflow_id='workflow_123',
            name='Test Workflow',
            description='Test workflow description',
            revision=Decimal('1'),
            workflow_type=WorkflowType.READONLY,
            created_by=self.user,
            modified_by=self.user,
            input_params={
                'onedataInputStore': 'input_store',
                'onedataOutputStore': 'output_store',
                'appConfig': '{"storeId": "config_store"}',
                'appConfigDetails': {}
            }
        )

        self.assertEqual(workflow.name, 'Test Workflow')
        self.assertEqual(workflow.onedata_workflow_id, 'workflow_123')
        self.assertEqual(workflow.revision, Decimal('1'))
        self.assertEqual(workflow.workflow_type, WorkflowType.READONLY)
        self.assertIsNotNone(workflow.id)

    def test_workflow_template_with_app_config_details(self):
        """Test workflow template with valid appConfigDetails"""
        workflow = WorkflowTemplate.objects.create(
            onedata_workflow_id='workflow_456',
            name='Workflow with Config',
            revision=Decimal('1'),
            workflow_type=WorkflowType.WRITE_DATA,
            created_by=self.user,
            modified_by=self.user,
            input_params={
                'onedataInputStore': 'input_store',
                'onedataOutputStore': 'output_store',
                'appConfig': '{"storeId": "config_store", "param1": "value1", "param2": 42}',
                'appConfigDetails': {
                    'param1': {
                        'type': 'string',
                        'description': 'First parameter'
                    },
                    'param2': {
                        'type': 'integer',
                        'description': 'Second parameter'
                    }
                }
            }
        )

        self.assertEqual(workflow.workflow_type, WorkflowType.WRITE_DATA)
        self.assertIn('appConfigDetails', workflow.input_params)
        self.assertEqual(len(workflow.input_params['appConfigDetails']), 2)

    def test_workflow_template_invalid_input_params(self):
        """Test workflow template with invalid input_params structure"""
        workflow = WorkflowTemplate(
            onedata_workflow_id='workflow_invalid',
            name='Invalid Workflow',
            revision=Decimal('1'),
            workflow_type=WorkflowType.READONLY,
            created_by=self.user,
            modified_by=self.user,
            input_params={
                'onedataInputStore': 'input_store',
                # Missing required fields
            }
        )

        with self.assertRaises(ValidationError):
            workflow.full_clean()

    def test_workflow_template_project_association(self):
        """Test many-to-many relationship with projects"""
        workflow = WorkflowTemplate.objects.create(
            onedata_workflow_id='workflow_789',
            name='Multi-project Workflow',
            revision=Decimal('1'),
            workflow_type=WorkflowType.READONLY,
            created_by=self.user,
            modified_by=self.user,
            input_params={
                'onedataInputStore': 'input_store',
                'onedataOutputStore': 'output_store',
                'appConfig': '{"storeId": "config_store"}',
                'appConfigDetails': {}
            }
        )

        # Add workflow to project
        self.project.workflow_templates.add(workflow)

        self.assertIn(workflow, self.project.workflow_templates.all())
        self.assertIn(self.project, workflow.supported_projects.all())

    def test_workflow_type_choices(self):
        """Test all workflow type choices"""
        types = [WorkflowType.WRITE_DATA, WorkflowType.READONLY,
                 WorkflowType.IN_PLACE_CHANGE, WorkflowType.EXPORT]

        for wf_type in types:
            workflow = WorkflowTemplate.objects.create(
                onedata_workflow_id=f'workflow_{wf_type}',
                name=f'Workflow {wf_type}',
                revision=Decimal('1'),
                workflow_type=wf_type,
                created_by=self.user,
                modified_by=self.user,
                input_params={
                    'onedataInputStore': 'input_store',
                    'onedataOutputStore': 'output_store',
                    'appConfig': '{"storeId": "config_store"}',
                    'appConfigDetails': {}
                }
            )
            self.assertEqual(workflow.workflow_type, wf_type)


class WorkflowParamsTest(TestCase):
    """Test suite for WorkflowParams validation"""

    def test_valid_workflow_params(self):
        """Test valid workflow params creation"""
        params = WorkflowParams(
            onedataInputStore='input_store',
            onedataOutputStore='output_store',
            appConfig='{"storeId": "config_store", "param1": "value"}',
            appConfigDetails={
                'param1': {
                    'type': 'string',
                    'description': 'Test parameter'
                }
            }
        )

        self.assertEqual(params.onedataInputStore, 'input_store')
        self.assertEqual(params.onedataOutputStore, 'output_store')

    def test_workflow_params_missing_store_id(self):
        """Test workflow params without storeId in appConfig"""
        with self.assertRaises(ValueError) as context:
            WorkflowParams(
                onedataInputStore='input_store',
                onedataOutputStore='output_store',
                appConfig='{"param1": "value"}',
                appConfigDetails={}
            )
        self.assertIn('storeId', str(context.exception))

    def test_workflow_params_invalid_json(self):
        """Test workflow params with invalid JSON in appConfig"""
        with self.assertRaises(ValueError) as context:
            WorkflowParams(
                onedataInputStore='input_store',
                onedataOutputStore='output_store',
                appConfig='invalid json',
                appConfigDetails={}
            )
        self.assertIn('valid JSON', str(context.exception))

    def test_workflow_params_unsupported_type(self):
        """Test workflow params with unsupported type in appConfigDetails"""
        with self.assertRaises(ValueError) as context:
            WorkflowParams(
                onedataInputStore='input_store',
                onedataOutputStore='output_store',
                appConfig='{"storeId": "store", "param1": "value"}',
                appConfigDetails={
                    'param1': {
                        'type': 'boolean',  # Unsupported type
                        'description': 'Test'
                    }
                }
            )
        self.assertIn('must be one of', str(context.exception))

    def test_workflow_params_missing_description(self):
        """Test workflow params with missing description"""
        with self.assertRaises(ValueError) as context:
            WorkflowParams(
                onedataInputStore='input_store',
                onedataOutputStore='output_store',
                appConfig='{"storeId": "store", "param1": "value"}',
                appConfigDetails={
                    'param1': {
                        'type': 'string'
                        # Missing description
                    }
                }
            )
        self.assertIn('description', str(context.exception))


class JobModelTest(TestCase):
    """Test suite for Job model"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(username='testuser', password='testpass')

        self.facility = Facility.objects.create(
            name='Test Facility',
            abbreviation='TF',
            created_by=self.user,
            modified_by=self.user,
            onedata_provider_url='https://oneprovider.test.com/api/v3/oneprovider',
            onedata_token='test_token_123'
        )

        self.project = Project.objects.create(
            facility=self.facility,
            name='Test Project',
            description='Test Description',
            created_by=self.user,
            modified_by=self.user,
            onedata_space_id='space123'
        )

        self.dataset = Dataset.objects.create(
            project=self.project,
            name='Test Dataset',
            description='Test Dataset Description',
            created_by=self.user,
            modified_by=self.user,
            onedata_file_id='file123'
        )

        self.experiment = Experiment.objects.create(
            dataset=self.dataset,
            name='Test Experiment',
            created_by=self.user,
            modified_by=self.user,
            onedata_file_id='exp_file123'
        )

        self.workflow_template = WorkflowTemplate.objects.create(
            onedata_workflow_id='workflow_123',
            name='Test Workflow',
            revision=Decimal('1'),
            workflow_type=WorkflowType.READONLY,
            created_by=self.user,
            modified_by=self.user,
            input_params={
                'onedataInputStore': 'input_store',
                'onedataOutputStore': 'output_store',
                'appConfig': '{"storeId": "config_store", "param1": "default_value", "param2": 100}',
                'appConfigDetails': {
                    'param1': {
                        'type': 'string',
                        'description': 'First parameter'
                    },
                    'param2': {
                        'type': 'integer',
                        'description': 'Second parameter'
                    }
                }
            }
        )

    def test_job_creation_with_project(self):
        """Test job creation with project as root resource"""
        job = Job.objects.create(
            workflow_template=self.workflow_template,
            root_resource_content_type=ContentType.objects.get_for_model(Project),
            root_resource_id=self.project.id,
            name='Test Job',
            description='Test job description',
            created_by=self.user,
            modified_by=self.user,
            app_config={'param1': 'test_value', 'param2': 50}
        )

        self.assertEqual(job.name, 'Test Job')
        self.assertEqual(job.status, JobStatus.NEW)
        self.assertEqual(job.root_resource_object, self.project)
        self.assertFalse(job.claimed)

    def test_job_creation_with_dataset(self):
        """Test job creation with dataset as root resource"""
        job = Job.objects.create(
            workflow_template=self.workflow_template,
            root_resource_content_type=ContentType.objects.get_for_model(Dataset),
            root_resource_id=self.dataset.id,
            name='Dataset Job',
            created_by=self.user,
            modified_by=self.user,
            app_config={'param1': 'test', 'param2': 42}
        )

        self.assertEqual(job.root_resource_object, self.dataset)

    def test_job_creation_with_experiment(self):
        """Test job creation with experiment as root resource"""
        job = Job.objects.create(
            workflow_template=self.workflow_template,
            root_resource_content_type=ContentType.objects.get_for_model(Experiment),
            root_resource_id=self.experiment.id,
            name='Experiment Job',
            created_by=self.user,
            modified_by=self.user,
            app_config={'param1': 'test', 'param2': 42}
        )

        self.assertEqual(job.root_resource_object, self.experiment)

    def test_job_invalid_root_resource_type(self):
        """Test job validation fails with invalid root resource type"""
        job = Job(
            workflow_template=self.workflow_template,
            root_resource_content_type=ContentType.objects.get_for_model(Facility),
            root_resource_id=self.facility.id,
            name='Invalid Job',
            created_by=self.user,
            modified_by=self.user,
            app_config={'param1': 'test', 'param2': 42}
        )

        with self.assertRaises(ValidationError) as context:
            job.full_clean()
        self.assertIn('root_resource_content_type', str(context.exception))

    def test_job_write_data_requires_output_resource(self):
        """Test that WriteData workflow requires output resource"""
        write_workflow = WorkflowTemplate.objects.create(
            onedata_workflow_id='write_workflow_123',
            name='Write Workflow',
            revision=Decimal('1'),
            workflow_type=WorkflowType.WRITE_DATA,
            created_by=self.user,
            modified_by=self.user,
            input_params={
                'onedataInputStore': 'input_store',
                'onedataOutputStore': 'output_store',
                'appConfig': '{"storeId": "config_store", "param1": "value"}',
                'appConfigDetails': {
                    'param1': {'type': 'string', 'description': 'Test param'}
                }
            }
        )

        job = Job(
            workflow_template=write_workflow,
            root_resource_content_type=ContentType.objects.get_for_model(Dataset),
            root_resource_id=self.dataset.id,
            name='Write Job',
            created_by=self.user,
            modified_by=self.user,
            app_config={'param1': 'test'}
            # Missing output_resource
        )

        with self.assertRaises(ValidationError) as context:
            job.full_clean()
        self.assertIn('output_resource', str(context.exception).lower())

    def test_job_app_config_validation(self):
        """Test job app_config validation against workflow template"""
        # Test with invalid field
        job = Job(
            workflow_template=self.workflow_template,
            root_resource_content_type=ContentType.objects.get_for_model(Dataset),
            root_resource_id=self.dataset.id,
            name='Invalid Config Job',
            created_by=self.user,
            modified_by=self.user,
            app_config={'param1': 'test', 'param2': 42, 'invalid_field': 'value'}
        )

        with self.assertRaises(ValidationError) as context:
            job.full_clean()
        self.assertIn('invalid_field', str(context.exception))

    def test_job_app_config_missing_required_field(self):
        """Test job app_config validation with missing required field"""
        job = Job(
            workflow_template=self.workflow_template,
            root_resource_content_type=ContentType.objects.get_for_model(Dataset),
            root_resource_id=self.dataset.id,
            name='Missing Field Job',
            created_by=self.user,
            modified_by=self.user,
            app_config={'param1': 'test'}  # Missing param2
        )

        with self.assertRaises(ValidationError) as context:
            job.full_clean()
        self.assertIn('param2', str(context.exception))

    def test_job_app_config_wrong_type(self):
        """Test job app_config validation with wrong type"""
        job = Job(
            workflow_template=self.workflow_template,
            root_resource_content_type=ContentType.objects.get_for_model(Dataset),
            root_resource_id=self.dataset.id,
            name='Wrong Type Job',
            created_by=self.user,
            modified_by=self.user,
            app_config={'param1': 'test', 'param2': 'not_an_integer'}
        )

        with self.assertRaises(ValidationError) as context:
            job.full_clean()
        self.assertIn('param2', str(context.exception))

    def test_job_status_transitions(self):
        """Test job status state machine transitions"""
        job = Job.objects.create(
            workflow_template=self.workflow_template,
            root_resource_content_type=ContentType.objects.get_for_model(Dataset),
            root_resource_id=self.dataset.id,
            name='Status Test Job',
            created_by=self.user,
            modified_by=self.user,
            app_config={'param1': 'test', 'param2': 42}
        )

        # NEW -> ASSIGNING
        job.set_status(JobStatus.ASSIGNING)
        self.assertEqual(job.status, JobStatus.ASSIGNING)

        # ASSIGNING -> ASSIGNED
        job.set_status(JobStatus.ASSIGNED)
        self.assertEqual(job.status, JobStatus.ASSIGNED)

        # ASSIGNED -> RUNNING
        job.set_status(JobStatus.RUNNING)
        self.assertEqual(job.status, JobStatus.RUNNING)

        # RUNNING -> SUCCESS
        job.set_status(JobStatus.SUCCESS)
        self.assertEqual(job.status, JobStatus.SUCCESS)

    def test_job_invalid_status_transition(self):
        """Test invalid job status transitions"""
        job = Job.objects.create(
            workflow_template=self.workflow_template,
            root_resource_content_type=ContentType.objects.get_for_model(Dataset),
            root_resource_id=self.dataset.id,
            name='Invalid Transition Job',
            created_by=self.user,
            modified_by=self.user,
            app_config={'param1': 'test', 'param2': 42}
        )

        # Try to go from NEW to RUNNING (invalid)
        with self.assertRaises(ValueError) as context:
            job.set_status(JobStatus.RUNNING)
        self.assertIn('Invalid transition', str(context.exception))

    def test_job_claim_mechanism(self):
        """Test job claiming mechanism for distributed processing"""
        job = Job.objects.create(
            workflow_template=self.workflow_template,
            root_resource_content_type=ContentType.objects.get_for_model(Dataset),
            root_resource_id=self.dataset.id,
            name='Claim Test Job',
            created_by=self.user,
            modified_by=self.user,
            app_config={'param1': 'test', 'param2': 42}
        )

        # First claim should succeed
        self.assertTrue(job.claim_job())
        self.assertTrue(job.claimed)
        self.assertIsNotNone(job.claimed_at)

        # Second claim should fail
        self.assertFalse(job.claim_job())

        # Unclaim the job
        job.unclaim_job()
        self.assertFalse(job.claimed)
        self.assertIsNone(job.claimed_at)

        # Should be able to claim again
        self.assertTrue(job.claim_job())

    def test_job_get_project_from_project(self):
        """Test get_project method when root resource is Project"""
        job = Job.objects.create(
            workflow_template=self.workflow_template,
            root_resource_content_type=ContentType.objects.get_for_model(Project),
            root_resource_id=self.project.id,
            name='Project Root Job',
            created_by=self.user,
            modified_by=self.user,
            app_config={'param1': 'test', 'param2': 42}
        )

        self.assertEqual(job.get_project(), self.project)

    def test_job_get_project_from_dataset(self):
        """Test get_project method when root resource is Dataset"""
        job = Job.objects.create(
            workflow_template=self.workflow_template,
            root_resource_content_type=ContentType.objects.get_for_model(Dataset),
            root_resource_id=self.dataset.id,
            name='Dataset Root Job',
            created_by=self.user,
            modified_by=self.user,
            app_config={'param1': 'test', 'param2': 42}
        )

        self.assertEqual(job.get_project(), self.project)

    def test_job_get_project_from_experiment(self):
        """Test get_project method when root resource is Experiment"""
        job = Job.objects.create(
            workflow_template=self.workflow_template,
            root_resource_content_type=ContentType.objects.get_for_model(Experiment),
            root_resource_id=self.experiment.id,
            name='Experiment Root Job',
            created_by=self.user,
            modified_by=self.user,
            app_config={'param1': 'test', 'param2': 42}
        )

        self.assertEqual(job.get_project(), self.project)

    def test_job_submission_counter(self):
        """Test job submission counter increments"""
        job = Job.objects.create(
            workflow_template=self.workflow_template,
            root_resource_content_type=ContentType.objects.get_for_model(Dataset),
            root_resource_id=self.dataset.id,
            name='Counter Test Job',
            created_by=self.user,
            modified_by=self.user,
            app_config={'param1': 'test', 'param2': 42}
        )

        self.assertEqual(job.job_submission_counter, 0)

        job.job_submission_counter += 1
        job.save()

        job.refresh_from_db()
        self.assertEqual(job.job_submission_counter, 1)

    def test_job_polling_counter(self):
        """Test job polling counter increments"""
        job = Job.objects.create(
            workflow_template=self.workflow_template,
            root_resource_content_type=ContentType.objects.get_for_model(Dataset),
            root_resource_id=self.dataset.id,
            name='Polling Test Job',
            created_by=self.user,
            modified_by=self.user,
            app_config={'param1': 'test', 'param2': 42}
        )

        self.assertEqual(job.job_polling_counter, 0)

        job.job_polling_counter += 1
        job.save()

        job.refresh_from_db()
        self.assertEqual(job.job_polling_counter, 1)

    def test_job_error_status_transitions(self):
        """Test transitions to error states"""
        job = Job.objects.create(
            workflow_template=self.workflow_template,
            root_resource_content_type=ContentType.objects.get_for_model(Dataset),
            root_resource_id=self.dataset.id,
            name='Error Status Job',
            created_by=self.user,
            modified_by=self.user,
            app_config={'param1': 'test', 'param2': 42}
        )

        # NEW -> SUBMISSION_ERROR
        job.set_status(JobStatus.SUBMISSION_ERROR)
        self.assertEqual(job.status, JobStatus.SUBMISSION_ERROR)

        # Create another job for POLLING_ERROR test
        job2 = Job.objects.create(
            workflow_template=self.workflow_template,
            root_resource_content_type=ContentType.objects.get_for_model(Dataset),
            root_resource_id=self.dataset.id,
            name='Polling Error Job',
            created_by=self.user,
            modified_by=self.user,
            app_config={'param1': 'test', 'param2': 42}
        )

        job2.set_status(JobStatus.ASSIGNING)
        job2.set_status(JobStatus.ASSIGNED)
        job2.set_status(JobStatus.RUNNING)

        # RUNNING -> POLLING_ERROR
        job2.set_status(JobStatus.POLLING_ERROR)
        self.assertEqual(job2.status, JobStatus.POLLING_ERROR)

    def test_job_recovery_transition(self):
        """Test recovery transition from ASSIGNING back to NEW"""
        job = Job.objects.create(
            workflow_template=self.workflow_template,
            root_resource_content_type=ContentType.objects.get_for_model(Dataset),
            root_resource_id=self.dataset.id,
            name='Recovery Test Job',
            created_by=self.user,
            modified_by=self.user,
            app_config={'param1': 'test', 'param2': 42}
        )

        job.set_status(JobStatus.ASSIGNING)
        self.assertEqual(job.status, JobStatus.ASSIGNING)

        # Recovery: ASSIGNING -> NEW
        job.set_status(JobStatus.NEW)
        self.assertEqual(job.status, JobStatus.NEW)


class AppConfigValidationTest(TestCase):
    """Test suite for app config value validation"""

    def test_validate_string_type(self):
        """Test string type validation"""
        # Valid string
        validate_app_config_value('test_value', 'string', 'test_field')

        # Invalid: not a string
        with self.assertRaises(ValueError) as context:
            validate_app_config_value(123, 'string', 'test_field')
        self.assertIn('must be a string', str(context.exception))

    def test_validate_integer_type(self):
        """Test integer type validation"""
        # Valid integer
        validate_app_config_value(42, 'integer', 'test_field')

        # Invalid: not an integer
        with self.assertRaises(ValueError) as context:
            validate_app_config_value('not_int', 'integer', 'test_field')
        self.assertIn('must be an integer', str(context.exception))

        # Invalid: boolean (should not be accepted as integer)
        with self.assertRaises(ValueError) as context:
            validate_app_config_value(True, 'integer', 'test_field')
        self.assertIn('must be an integer', str(context.exception))

    def test_validate_float_type(self):
        """Test float type validation"""
        # Valid float
        validate_app_config_value(3.14, 'float', 'test_field')

        # Valid: integer accepted as float
        validate_app_config_value(42, 'float', 'test_field')

        # Invalid: not a number
        with self.assertRaises(ValueError) as context:
            validate_app_config_value('not_float', 'float', 'test_field')
        self.assertIn('must be a number', str(context.exception))

        # Invalid: boolean
        with self.assertRaises(ValueError) as context:
            validate_app_config_value(True, 'float', 'test_field')
        self.assertIn('must be a number', str(context.exception))

    def test_validate_unsupported_type(self):
        """Test validation with unsupported type"""
        with self.assertRaises(ValueError) as context:
            validate_app_config_value('value', 'boolean', 'test_field')
        self.assertIn('Unsupported type', str(context.exception))


class JobStatusTest(TestCase):
    """Test JobStatus enum"""

    def test_job_status_choices(self):
        """Test all JobStatus choices are available"""
        statuses = [
            JobStatus.NEW,
            JobStatus.ASSIGNING,
            JobStatus.ASSIGNED,
            JobStatus.RUNNING,
            JobStatus.SUCCESS,
            JobStatus.FAILURE,
            JobStatus.SUBMISSION_ERROR,
            JobStatus.POLLING_ERROR
        ]

        choices = JobStatus.choices()
        self.assertEqual(len(choices), len(statuses))

        for status in statuses:
            self.assertIn(status, [choice[0] for choice in choices])


class JobLogLevelTest(TestCase):
    """Test JobLogLevel enum"""

    def test_job_log_level_choices(self):
        """Test all JobLogLevel choices are available"""
        levels = [
            JobLogLevel.DEBUG,
            JobLogLevel.INFO,
            JobLogLevel.WARNING
        ]

        choices = JobLogLevel.choices()
        self.assertEqual(len(choices), len(levels))

        for level in levels:
            self.assertIn(level, [choice[0] for choice in choices])
