import uuid
import datetime
from django.db import models
from django_extensions.db.models import TimeStampedModel
from django.contrib.auth.models import User
from django.conf import settings

##
# Steps to generate UML class diagram
#
# In running container:
#
# apt update && apt install graphviz
# pip3 install pydotplus
# only one given app
# pyma graph_models api --exclude-models TimeStampedModel --pydot --arrow-shape normal --color-code-deletions -o dareg.png
# all apps
# pyma graph_models api --all-applications --group-models --pydot --arrow-shape normal --color-code-deletions -o dareg_full.png
##


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
    deleted = models.DateTimeField(null=True, blank=True, default=None, db_index=True)
    deleted_by = models.ForeignKey(
        User,
        models.PROTECT,
        related_name="%(class)s_deleted_by",
        null=True,
        blank=True,
        default=None,
    )

    def delete(self, *args, **kwargs):
        """
        Soft delete object
        """
        self.deleted = datetime.now()
        # save user who deleted the object if available
        if "user" in kwargs and isinstance(kwargs.get("user"), User):
            self.deleted_by = kwargs.get("user")

        super().save(*args, **kwargs)

    class Meta:
        abstract = True


class Facility(BaseModel):
    name = models.CharField("Name", max_length=200, unique=True)
    abbreviation = models.CharField("Abbreviation", max_length=20, unique=True)

    class Meta:
        verbose_name_plural = "Facilities"


class Schema(BaseModel):
    version = models.PositiveIntegerField("Version", default=1)
    name = models.CharField("Name", max_length=200)
    description = models.CharField("Description", max_length=500, null=True, blank=True)
    schema = models.JSONField(blank=False, null=False, default=dict)
    uischema = models.JSONField(default=dict)


class Metadata(BaseModel):
    schema = models.ForeignKey(Schema, models.PROTECT)
    data = models.JSONField(blank=False, null=False, default=dict)


class Project(BaseModel):
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
    project_schema = models.ForeignKey(
        Schema, models.PROTECT, null=True, blank=True, related_name="project_schema"
    )
    metadata = models.JSONField(blank=False, null=False, default=dict)


class Dataset(BaseModel):
    project = models.ForeignKey(Project, models.PROTECT)
    name = models.CharField("Name", max_length=200)
    description = models.CharField("Description", max_length=500)
    dataset_schema = models.ForeignKey(Schema, models.PROTECT, null=True, blank=True)
    metadata = models.JSONField(blank=False, null=False, default=dict)


class Language(models.Model):
    name = models.CharField("Name", max_length=200, unique=True)
    code = models.CharField(
        "ISO code", max_length=2, unique=True, db_comment="ISO 639-1"
    )
    priority = models.PositiveSmallIntegerField(
        default=None, blank=True, null=True, unique=True
    )


class UserProfile(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, models.PROTECT)
    full_name = models.CharField("Full name", max_length=200)
    language = models.ForeignKey(Language, models.PROTECT, null=True, blank=True)
