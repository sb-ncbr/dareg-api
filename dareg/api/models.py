from django.db import models
from django_extensions.db.models import TimeStampedModel
from django.conf import settings


class Facility(TimeStampedModel):
    name = models.CharField("Name", max_length=200, unique=True)
    abbreviation = models.CharField("Abbreviation", max_length=20, unique=True)


class Template(TimeStampedModel):
    name = models.CharField("Name", max_length=200)
    json = models.JSONField()


class FilledTemplate(TimeStampedModel):
    template = models.ForeignKey(Template, models.PROTECT)
    json = models.JSONField()


class Project(TimeStampedModel):
    facility = models.ForeignKey(Facility, models.PROTECT)
    name = models.CharField("Name", max_length=200)
    description = models.CharField("Description", max_length=500)
    default_template = models.ForeignKey(Template, models.PROTECT)
    default_filled_template = models.ForeignKey(FilledTemplate, models.PROTECT)


class Dataset(TimeStampedModel):
    project = models.ForeignKey(Project, models.PROTECT)
    name = models.CharField("Name", max_length=200)
    description = models.CharField("Description", max_length=500)


class Language(TimeStampedModel):
    name = models.CharField("Name", max_length=200, unique=True)
    code = models.CharField("ISO code", max_length=2, unique=True, db_comment="ISO 639-1")
    priority = models.PositiveSmallIntegerField(default=None, blank=True, null=True, unique=True)


class UserProfile(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, models.PROTECT)
    full_name = models.CharField("Full name", max_length=200)
