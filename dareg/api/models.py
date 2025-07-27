import base64
import hashlib
import os
import uuid
import datetime
from enum import StrEnum
import logging

from django.db import models
from django_extensions.db.models import TimeStampedModel
from django.contrib.auth.models import User, Group, Permission
from django.dispatch import receiver
from django.db.models.signals import post_save, post_delete
from django.conf import settings
from guardian.shortcuts import assign_perm
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

##
# Steps to generate UML class diagram
#
# In running container:
#
# apt update && apt install graphviz
# pip3 install pydotplus
# only one given app
# pyma graph_models --exclude-models TimeStampedModel,BaseModel,User --pydot --arrow-shape normal --disable-abstract-fields --color-code-deletions -o dareg.png api
# pyma graph_models api --all-applications --group-models --pydot --arrow-shape normal --color-code-deletions -o dareg_full.png
##
logger = logging.getLogger(__name__)

class BaseModel(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(
        User,
        models.PROTECT,
        related_name="%(class)s_created_by",
        null=True,
        blank=True,
        default=None,
    )
    modified_by = models.ForeignKey(
        User,
        models.PROTECT,
        related_name="%(class)s_modified_by",
        null=True,
        blank=True,
        default=None,
    )

    """
    def delete(self, *args, **kwargs):
        
        #Delete object and log deletion. 

        # TODO - insert record of deletion to log

        super().save(*args, **kwargs)
    """

    class Meta:
        abstract = True


def is_stronger_perm(perm1, perm2):
    permission_hierarchy = {"none": 0, "viewer": 1, "editor": 2, "owner": 3}
    return permission_hierarchy[perm1] > permission_hierarchy[perm2]


class PermsObject(BaseModel):
    """
    Objects for which permissions are managed. 
    """

    def save(self, *args, **kwargs):
        
        super().save(*args, **kwargs)

        # Creating PermsGroup for new PermsObject
        if not PermsGroup.objects.filter(name=f"{self.id}_owner").exists():
            ownerGroup = PermsGroup.objects.create(name=f"{self.id}_owner", content_object=self, role=PermsGroup.OWNER)
            # add user who created the object to owners
            ownerGroup.save()

            ownerGroup.user_set.add(self.created_by)

        
        if not PermsGroup.objects.filter(name=f"{self.id}_editor").exists():
            PermsGroup.objects.create(name=f"{self.id}_editor", content_object=self, role=PermsGroup.EDITOR)

        if not PermsGroup.objects.filter(name=f"{self.id}_viewer").exists():
            PermsGroup.objects.create(name=f"{self.id}_viewer", content_object=self, role=PermsGroup.VIEWER)
        
    def max_perm(self, request, current_perm="none"):

        higher_level = {
            "experiment": Dataset,
            "dataset": Project,
            "project": Facility,
            "facility": None
        }

        for x in [["owner", "delete"], ["editor", "change"], ["viewer", "view"]]:
            
            if x == current_perm:
                break
            
            if self.is_permission_stronger(current_perm, request, x):
                current_perm = x[0]
                break
        
        upper_obj = higher_level[self.__class__.__name__.lower()]
        
        if not upper_obj:
            return current_perm
        
        obj = getattr(self, upper_obj.__name__.lower())
        
        return obj.max_perm(request, current_perm)

    def is_permission_stronger(self, current_perm, request, x):
        return request.user.has_perm(f"{x[1]}_{self.__class__.__name__.lower()}", self) and is_stronger_perm(x[0],
                                                                                                             current_perm)

    def perm_atleast(self, request, role):
        perm = self.max_perm(request)
        match role:
            case PermsGroup.OWNER:
                return perm in ["owner"]
            case PermsGroup.EDITOR:
                return perm in ["owner", "editor"]
            case PermsGroup.VIEWER:
                return perm in ["owner", "editor", "viewer"]
    
    def delete(self, *args, **kwargs):
        # delete PermsGroups
        PermsGroup.objects.filter(object_id=self.id).delete()
    
        super().delete(*args, **kwargs)

    class Meta:
        abstract = True

class PermsGroup(Group):
    """
    The group we use to control user permissions to PermsObjects. 
    """

    object_id = models.UUIDField(
        editable=False,
        help_text="Object id",
        null=True,
    )

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        help_text="Content type of the model",
        null=True,
    )

    content_object = GenericForeignKey('content_type', 'object_id')

    OWNER = "Owner"
    EDITOR = "Editor"
    VIEWER = "Viewer"
    ROLE_CHOICES = [
        (OWNER, "Owner"),
        (EDITOR, "Editor"),
        (VIEWER, "Viewer"),
    ]
    role = models.CharField(max_length=6, choices=ROLE_CHOICES, null=True)

    def save(self, *args, **kwargs):

        super().save(*args, **kwargs)

        # assign permissions
        class_name = self.content_object._meta.verbose_name.lower()

        if self.role == self.OWNER:
            logger.info(f"Assigning permission: delete_{class_name}, group: {self}, object: {self.content_object}")
            assign_perm(f"delete_{class_name}", self, self.content_object)
        
        if self.role == self.OWNER or self.role == self.EDITOR:
            assign_perm(f"change_{class_name}", self, self.content_object)
        
        assign_perm(f"view_{class_name}", self, self.content_object)

    def __str__(self):
        return f'{self.content_type.model_class()._meta.verbose_name.capitalize()} - {self.content_object} - {self.role}'

class Facility(PermsObject):
    name = models.CharField("Name", max_length=200, unique=True)
    abbreviation = models.CharField("Abbreviation", max_length=20, unique=True)
    web = models.URLField("Web", max_length=200, blank=True)
    email = models.EmailField("Email", max_length=200, blank=True)
    logo = models.URLField("Logo", blank=True, max_length=200)
    onedata_token = models.CharField("Onedata Secret token", max_length=512, blank=True)
    onedata_provider_url = models.URLField("Onedata provider URL", max_length=200, blank=True)

    class Meta:
        verbose_name_plural = "Facilities"

    def __str__(self):
        return f'{self.name}'
    
    trigram_search_fields = ["name", "abbreviation", "web", "email"]

class Instrument(PermsObject):
    facility = models.ForeignKey(Facility, models.PROTECT)
    name = models.CharField("Name", max_length=200)
    method = models.CharField("Method", max_length=500)
    support = models.CharField("Support", max_length=500)
    contact = models.CharField("Contact", max_length=500)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, models.PROTECT)
    default_data_dir = models.CharField("Default data directory", max_length=1024, default="/data")

    class Meta:
        unique_together = ("facility", "name")

    def __str__(self):
        return f'{self.name}'

class Schema(BaseModel):
    version = models.PositiveIntegerField("Version", default=1)
    name = models.CharField("Name", max_length=200)
    description = models.CharField("Description", max_length=500, null=True, blank=True)
    schema = models.JSONField(default=dict)
    uischema = models.JSONField(default=dict)

    trigram_search_fields = ["name", "description"]

    class Meta:
        unique_together = ("name", "version")

    def __str__(self):
            return f'{self.name} (v.{self.version})'


class Project(PermsObject):
    facility = models.ForeignKey(Facility, models.PROTECT)
    name = models.CharField("Name", max_length=200)
    description = models.CharField("Description", max_length=500)
    default_dataset_schema = models.ForeignKey(
        Schema,
        models.PROTECT,
        null=True,
        blank=True,
        related_name="default_dataset_schema",
    )
    onedata_space_id = models.CharField("Onedata space ID", max_length=200, blank=True)

    trigram_search_fields = ["name", "description"]
    
    class Meta:
        unique_together = ("facility", "name")

    def __str__(self):
        return f'{self.name}'


class Tag(BaseModel):
    name = models.CharField("Name", max_length=50, unique=True)
    description = models.CharField("Description", max_length=200, blank=True)


class MetadataExtractor(BaseModel):
    name = models.CharField("Name", max_length=200, unique=True)

class DatasetStatus(StrEnum):
    NEW = "new"
    FINISHED = "finished"

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]

class Dataset(PermsObject):
    project = models.ForeignKey(Project, models.PROTECT)
    name = models.CharField("Name", max_length=200)
    description = models.CharField("Description", max_length=500)
    schema = models.ForeignKey(Schema, models.PROTECT, null=True, blank=True)
    metadata = models.JSONField(blank=False, null=False, default=dict)
    tags = models.ManyToManyField(Tag, blank=True)
    onedata_file_id = models.CharField("Onedata File ID", max_length=512, null=True, blank=True)
    onedata_share_id = models.CharField("Onedata Default Share ID", max_length=512, null=True, blank=True)
    onedata_dataset_id = models.CharField("Onedata Dataset ID", max_length=512, null=True, blank=True)
    onedata_space_id = models.CharField("Onedata Space ID", max_length=512, null=True, blank=True)
    doi = models.CharField("DOI", max_length=50, null=True, blank=True)
    reservationId = models.CharField("Reservation ID", max_length=50, null=True, blank=True)
    status = models.CharField(choices=DatasetStatus.choices(), default=DatasetStatus.NEW, max_length=20)

    trigram_search_fields = ["name", "description"]

    def __str__(self):
        return f'{self.name}'
  
    @property
    def onedata_visit_id(self):
        space_id = self.onedata_space_id if self.onedata_space_id else self.project.onedata_space_id
        to_base64 = f"guid#{self.onedata_dataset_id}#{space_id}"
        return base64.b64encode(to_base64.encode())
    
    @property
    def onedata_space_id(self):
        return self.__dict__.get("onedata_space_id") or self.project.onedata_space_id

    class Meta:
        unique_together = ("project", "name")


class ExperimentStatus(StrEnum):
    NEW = "new"
    PREPARED = "prepared"
    RUNNING = "running"
    SYNCHRONIZING = "synchronizing"
    SUCCESS = "success"
    FAILURE = "failure"
    DISCARDED = "discarded"

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]

class Experiment(PermsObject):
    dataset = models.ForeignKey(Dataset, models.PROTECT)
    name = models.CharField("Name", max_length=200, blank=True)
    start_time = models.DateTimeField("Start Time", max_length=200, null=True, blank=True)
    end_time = models.DateTimeField("End Time", max_length=200, null=True, blank=True)
    note = models.CharField("Note", max_length=500, blank=True)
    status = models.CharField(choices=ExperimentStatus.choices(), default=ExperimentStatus.NEW, max_length=20)
    onedata_file_id = models.CharField("Onedata File ID", max_length=512, null=True, blank=True)

    trigram_search_fields = ["name", "note"]

class Language(models.Model):
    name = models.CharField("Name", max_length=200, unique=True)
    code = models.CharField(
        "ISO code", max_length=2, unique=True, db_comment="ISO 639-1"
    )
    priority = models.PositiveSmallIntegerField(
        default=None, blank=True, null=True, unique=True
    )


class UserProfile(BaseModel):
    class TableRowsOptions(models.IntegerChoices):
        VALUE1 = 25
        VALUE2 = 50
        VALUE3 = 100
        VALUE4 = 250

    THEME_CHOICES = [
        ('dark', 'Dark'),
        ('light', 'Light'),
        ('system', 'System'),
    ]

    LANG_CHOICES = [
        ('cs-CZ', 'Czech'),
        ('en-US', 'English'),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, models.PROTECT)
    full_name = models.CharField("Full name", max_length=200)
    language = models.ForeignKey(Language, models.PROTECT, null=True, blank=True)
    default_data_rows = models.IntegerField(choices=TableRowsOptions.choices, default=TableRowsOptions.VALUE1)
    default_theme = models.CharField(max_length=6, choices=THEME_CHOICES, default='light')
    default_lang = models.CharField(max_length=5, choices=LANG_CHOICES, default='en-US')

    @property
    def app_version(self):
        return {
            "version": os.getenv("APP_VERSION", "0.0.0"),
            "date": os.getenv("APP_VERSION_DATE", datetime.datetime.now().strftime("%Y-%m-%d")),
            "environment": os.getenv("APP_ENV", "local"),
        }
    
    @property
    def avatar(self):
        return f"https://www.gravatar.com/avatar/{hashlib.sha256(self.user.email.lower().encode()).hexdigest()}"

    @property
    def last_login(self):
        return self.user.last_login

    def __str__(self):
        return f'{self.full_name}'
    
    @receiver(post_save, sender=User)
    def create_profile(sender, instance, created, **kwargs):
        try:
            if created:
                UserProfile.objects.create(user=instance, full_name=f'{instance.first_name} {instance.last_name}').save()
            else:
                if instance.userprofile.full_name == "":
                    instance.userprofile.full_name = f'{instance.first_name} {instance.last_name}'
                    instance.userprofile.save()
        except Exception as err:
            print(f'Error creating user profile!\n{err}')

    @receiver(post_delete, sender=User)
    def save_profile(sender, instance, **kwargs):
        try:
            instance.userprofile.delete()
        except Exception as err:
            print(f'Error saving user profile!\n{err}')

    def __str__(self):
        return f'{self.full_name}'
    
class WorkflowTemplate(PermsObject):
    project_id = models.ForeignKey(Project, models.PROTECT)
    workflow_id = models.CharField("Workflow ID", max_length=200, unique=True)
    name = models.CharField("Name", max_length=200, blank=True)
    description = models.CharField("Description", max_length=500, blank=True)
    revision = models.DecimalField("Revision", max_digits=10, decimal_places=0, default=1)
    input_params = models.JSONField("JSON", default=dict, blank=True)

    class Meta:
        verbose_name = "workflowtemplate"
        verbose_name_plural = "workflowtemplates"
    
    def clean(self):
        
        logger.info("Creating a new workflow template")
        # Verify that the workflow with id workflow_id exists in onedata
        workflow_id = self.id
        
        """ Verify the workflow has inputsTemplate in schema like:
        # {
        #  "inputFile": "store_id",
        #  "outputFile": "store_id",
        #  "appConfig": "JSON config"
        # }
        """
        # log verifying inputsTemplate
        # verify_workflow_template(self)

class JobStatus(StrEnum):
    NEW = "new"
    RUNNING = "running"
    # TODO: Implement scheduling state
    SCHEDULING = "scheduling"
    SUCCESS = "success"
    FAILURE = "failure"

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]
    
class JobLogLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]
    
class Job(PermsObject):
    workflow_temaplate_id = models.ForeignKey(WorkflowTemplate, models.PROTECT)
    workflow_id = models.CharField("Workflow ID", max_length=200)
    # Generic relation to Project, Dataset, or Experiment
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        help_text="Content type of the related object (Project, Dataset, or Experiment)",
        null=True,
        blank=True,
    )
    object_id = models.UUIDField(
        help_text="ID of the related object (Project, Dataset, or Experiment)",
        null=True,
        blank=True,
    )
    workflow_execution_id = models.CharField("Workflow Execution ID", max_length=200, blank=True, null=True, editable=False)
    content_object = GenericForeignKey('content_type', 'object_id')
    name = models.CharField("Name", max_length=200)
    description = models.CharField("Description", max_length=500, blank=True)
    status = models.CharField(choices=JobStatus.choices(), default=JobStatus.NEW, max_length=20, editable=False)
    input_params = models.JSONField("JSON", default=dict)
    start_time = models.DateTimeField("Start Time", max_length=200, null=True, blank=True, editable=False)
    end_time = models.DateTimeField("End Time", max_length=200, null=True, blank=True, editable=False)
    log_level = models.CharField(choices=JobLogLevel.choices(), default=JobLogLevel.INFO, max_length=20, blank=True)


    def clean(self):
        # Enforce that content_type is only Experiment, Dataset, or Project
        allowed_models = {"experiment", "dataset", "project"}
        model_name = self.content_type.model
        if model_name not in allowed_models:
            from django.core.exceptions import ValidationError
            raise ValidationError({
                "content_type": f"Job can only be related to Experiment, Dataset, or Project, not '{model_name}'."
            })

        # Check permissions for the workflow template creation
    
    def set_status(self, new_status):
        """
        Change the status of the job to a new valid state.
        Args:
            new_status (str): The new status to set. Must be a valid JobStatus value.
            save (bool): Whether to save the model after changing status. Default True.
        Raises:
            ValueError: If new_status is not a valid JobStatus value.
        """
        valid_statuses = {status.value for status in JobStatus}
        if new_status not in valid_statuses:
            raise ValueError(f"Invalid job status: {new_status}. Must be one of: {valid_statuses}")
        
        if self.status == new_status:
            logger.info(f"Job {self.id} status is already {new_status}. No change needed.")
            return
        if self.status == JobStatus.NEW and new_status == JobStatus.RUNNING:
            self.status = new_status
        elif self.status == JobStatus.RUNNING and new_status in [JobStatus.SUCCESS, JobStatus.FAILURE]:
            self.status = new_status
        else:
            raise ValueError(f"Cannot change job status from {self.status} to {new_status}. Invalid transition.")
        
        self.save(update_fields=["status"])


# create a class that represents job input parameters inputFile, outputFile, 
class JobParams:
    def __init__(self, inputFile: str, outputFile: str, appConfig: str):
        if not inputFile or not isinstance(inputFile, str) or not inputFile.strip():
            raise ValueError("inputFile must be a non-empty string")
        if not outputFile or not isinstance(outputFile, str) or not outputFile.strip():
            raise ValueError("outputFile must be a non-empty string")
        if not appConfig or not isinstance(appConfig, str) or not appConfig.strip():
            raise ValueError("appConfig must be a non-empty string")
        self.inputFile = inputFile
        self.outputFile = outputFile
        self.appConfig = appConfig

    @classmethod
    def from_dict(cls, data):
        return cls(
            inputFile=data.get('inputFile'),
            outputFile=data.get('outputFile'),
            appConfig=data.get('appConfig')
        )
