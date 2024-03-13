import uuid
import datetime
from django.db import models
from django_extensions.db.models import TimeStampedModel
from django.contrib.auth.models import User, Group
from django.conf import settings
from guardian.shortcuts import assign_perm

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


class PermsObject(BaseModel):

    def save(self, *args, **kwargs):
        """
        from .permissions import max_perm
        perm_level = {
            "owner": 3,
            "editor": 2,
            "viewer": 1,
            "none": 0
        }

        perm_level[max_per,(self, self.created_by)] >= 2
        """

        super().save(*args, **kwargs)

        if not PermsGroup.objects.filter(name=f"{self.id}_owner").exists():

            ownerGroup = PermsGroup.objects.create(name=f"{self.id}_owner")
            assign_perm('owner', ownerGroup, self)
            assign_perm('editor', ownerGroup, self)
            assign_perm('viewer', ownerGroup, self)
            ownerGroup.save()

            editorGroup = PermsGroup.objects.create(name=f"{self.id}_editor")
            assign_perm('editor', editorGroup, self)
            assign_perm('viewer', editorGroup, self)
            editorGroup.save()

            viewerGroup = PermsGroup.objects.create(name=f"{self.id}_viewer")
            assign_perm('viewer', viewerGroup, self)
            viewerGroup.save()

            #self.created_by.groups.add(ownerGroup)
            ownerGroup.user_set.add(self.created_by)

    def delete(self, *args, **kwargs):
        for x in ["owner", "editor", "viewer"]:
            PermsGroup.objects.get(name=f"{self.id}_{x}").delete()
    
        super().delete(*args, **kwargs)

    class Meta:
        abstract = True


class PermsGroup(Group):
    
    @property
    def object(self):
        return self.name.split("_")[0]
    
    @property
    def level(self):
        return self.name.split("_")[1]


class Facility(PermsObject):
    name = models.CharField("Name", max_length=200, unique=True)
    abbreviation = models.CharField("Abbreviation", max_length=20, unique=True)
    web = models.URLField("Web", max_length=200, blank=True)
    email = models.EmailField("Email", max_length=200, blank=True)

    class Meta:
        verbose_name_plural = "Facilities"
        permissions = (
            ('owner', 'Owner'),
            ('editor', 'Editor'),
            ('viewer', 'Viewer'),
        )


class Schema(BaseModel):
    version = models.PositiveIntegerField("Version", default=1)
    name = models.CharField("Name", max_length=200)
    description = models.CharField("Description", max_length=500, null=True, blank=True)
    schema = models.JSONField(default=dict)
    uischema = models.JSONField(default=dict)

    class Meta:
        unique_together = ("name", "version")


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

    class Meta:
        unique_together = ("facility", "name")
        permissions = (
            ('owner', 'Owner'),
            ('editor', 'Editor'),
            ('viewer', 'Viewer'),
        )


class Tag(BaseModel):
    name = models.CharField("Name", max_length=50, unique=True)
    description = models.CharField("Description", max_length=200, blank=True)


class MetadataExtractor(BaseModel):
    name = models.CharField("Name", max_length=200, unique=True)


class Dataset(PermsObject):
    project = models.ForeignKey(Project, models.PROTECT)
    name = models.CharField("Name", max_length=200)
    description = models.CharField("Description", max_length=500)
    schema = models.ForeignKey(Schema, models.PROTECT, null=True, blank=True)
    metadata = models.JSONField(blank=False, null=False, default=dict)
    tags = models.ManyToManyField(Tag, blank=True)

    class Meta:
        permissions = (
            ('owner', 'Owner'),
            ('editor', 'Editor'),
            ('viewer', 'Viewer'),
        )

class Language(models.Model):
    name = models.CharField("Name", max_length=200, unique=True)
    code = models.CharField(
        "ISO code", max_length=2, unique=True, db_comment="ISO 639-1"
    )
    priority = models.PositiveSmallIntegerField(
        default=None, blank=True, null=True, unique=True
    )


class UserProfile(TimeStampedModel):
    class TableRowsOptions(models.IntegerChoices):
        VALUE1 = 25
        VALUE2 = 50
        VALUE3 = 100
        VALUE4 = 250

    user = models.OneToOneField(settings.AUTH_USER_MODEL, models.PROTECT)
    full_name = models.CharField("Full name", max_length=200)
    language = models.ForeignKey(Language, models.PROTECT, null=True, blank=True)
    default_data_rows = models.IntegerField(choices=TableRowsOptions.choices, default=TableRowsOptions.VALUE1)
