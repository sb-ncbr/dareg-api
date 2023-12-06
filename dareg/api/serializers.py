from django.contrib.auth.models import User, Group
from rest_framework import serializers
from .models import Facility, Metadata, Project, Dataset, Schema

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["username", "email", "groups"]


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ["name"]


class FacilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Facility
        fields = "__all__"


class MinimalSchemaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Schema
        fields = ["id", "name", "description"]


class SchemaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Schema
        fields = "__all__"


class MinimalMetadataSerializer(serializers.ModelSerializer):
    class Meta:
        fields = ["id"]


class MetadataResponseSerializer(serializers.ModelSerializer):
    template = SchemaSerializer(read_only=True)

    class Meta:
        model = Metadata
        fields = "__all__"


class MetadataSerializer(serializers.ModelSerializer):
    class Meta:
        model = Metadata
        fields = "__all__"

    def to_representation(self, data):
        """Serialize the facility as a nested object."""
        return MetadataResponseSerializer(context=self.context).to_representation(
            data
        )


class ProjectResponseSerializer(serializers.ModelSerializer):
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


class DatasetResponseSerializer(serializers.ModelSerializer):
    project = MinimalSchemaSerializer(read_only=True)
    dataset_schema = MinimalSchemaSerializer(read_only=True)

    class Meta:
        model = Dataset
        fields = "__all__"
    
class DatasetSerializer(serializers.ModelSerializer):

    class Meta:
        model = Dataset
        fields = "__all__"

    def to_representation(self, data):
        return DatasetResponseSerializer(context=self.context).to_representation(data)