from django.contrib.auth.models import User, Group
from rest_framework import serializers
from .models import Facility, Metadata, Project, Dataset, Schema


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


class MinimalSchemaSerializer(MinimalHyperlinkedModelSerialized):
    class Meta:
        model = Schema
        fields = ["id", "name", "url"]


class SchemaSerializer(HyperlinkedModelSerializerWithId):
    class Meta:
        model = Schema
        fields = "__all__"


class MinimalMetadataSerializer(MinimalHyperlinkedModelSerialized):
    class Meta:
        model = Schema
        fields = ["id", "url"]


class MetadataResponseSerializer(HyperlinkedModelSerializerWithId):
    template = SchemaSerializer(read_only=True)

    class Meta:
        model = Metadata
        fields = "__all__"


class MetadataSerializer(HyperlinkedModelSerializerWithId):
    class Meta:
        model = Metadata
        fields = "__all__"

    def to_representation(self, data):
        """Serialize the facility as a nested object."""
        return MetadataResponseSerializer(context=self.context).to_representation(
            data
        )


class ProjectResponseSerializer(HyperlinkedModelSerializerWithId):
    facility = FacilitySerializer(read_only=True)
    default_dataset_schema = MinimalSchemaSerializer(read_only=True)
    project_schema = MinimalSchemaSerializer(read_only=True)
    project_metadata = MetadataSerializer(read_only=True)

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


class DatasetResponseSerializer(HyperlinkedModelSerializerWithId):
    project = MinimalSchemaSerializer(read_only=True)
    dataset_schema = MinimalSchemaSerializer(read_only=True)

    class Meta:
        model = Dataset
        fields = "__all__"
    
class DatasetSerializer(HyperlinkedModelSerializerWithId):

    class Meta:
        model = Dataset
        fields = "__all__"

    def to_representation(self, data):
        return DatasetResponseSerializer(context=self.context).to_representation(data)