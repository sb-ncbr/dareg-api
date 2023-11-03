from django.contrib.auth.models import User, Group
from rest_framework import serializers
from .models import Facility, FilledTemplate, Project, Dataset, Template


class HyperlinkedModelSerializerWithId(serializers.HyperlinkedModelSerializer):
    """Extend the HyperlinkedModelSerializer to add IDs as well for the best of
    both worlds.
    """

    id = serializers.ReadOnlyField()


class MinimalHyperlinkedModelSerialized(serializers.HyperlinkedModelSerializer):
    """Extend the HyperlinkedModelSerializer to add IDs as well for the best of
    both worlds.
    """

    id = serializers.ReadOnlyField()


class UserSerializer(HyperlinkedModelSerializerWithId):
    class Meta:
        model = User
        fields = ["url", "username", "email", "groups"]


class GroupSerializer(HyperlinkedModelSerializerWithId):
    class Meta:
        model = Group
        fields = ["url", "name"]


class FacilitySerializer(HyperlinkedModelSerializerWithId):
    class Meta:
        model = Facility
        fields = "__all__"


class MinimalTemplateSerializer(MinimalHyperlinkedModelSerialized):
    class Meta:
        model = Template
        fields = ["id", "name", "url"]


class TemplateSerializer(HyperlinkedModelSerializerWithId):
    class Meta:
        model = Template
        fields = "__all__"


class MinimalFilledTemplateSerializer(MinimalHyperlinkedModelSerialized):
    class Meta:
        model = Template
        fields = ["id", "url"]


class FilledTemplateResponseSerializer(HyperlinkedModelSerializerWithId):
    template = TemplateSerializer(read_only=True)

    class Meta:
        model = FilledTemplate
        fields = "__all__"


class FilledTemplateSerializer(HyperlinkedModelSerializerWithId):
    class Meta:
        model = FilledTemplate
        fields = "__all__"

    def to_representation(self, data):
        """Serialize the facility as a nested object."""
        return FilledTemplateResponseSerializer(context=self.context).to_representation(
            data
        )


class ProjectResponseSerializer(HyperlinkedModelSerializerWithId):
    facility = FacilitySerializer(read_only=True)
    default_dataset_template = MinimalTemplateSerializer(read_only=True)
    project_template = MinimalTemplateSerializer(read_only=True)
    project_filled_template = FilledTemplateSerializer(read_only=True)

    class Meta:
        model = Project
        fields = "__all__"


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = "__all__"

    def to_representation(self, data):
        """Serialize the facility as a nested object."""
        return ProjectResponseSerializer(context=self.context).to_representation(data)


class DatasetSerializer(HyperlinkedModelSerializerWithId):
    class Meta:
        model = Dataset
        fields = "__all__"
