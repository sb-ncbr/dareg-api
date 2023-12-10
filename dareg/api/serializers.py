from django.contrib.auth.models import User, Group
from rest_framework import serializers
from .models import Facility, Project, Dataset, Schema, BaseModel

class UserSerializerMinimal(serializers.ModelSerializer):

    full_name = serializers.SerializerMethodField()

    def get_full_name(self, obj):
        return '{} {}'.format(obj.first_name, obj.last_name)

    class Meta:
        model = User
        fields = ["id", "full_name"]


class BaseModelSerializer(serializers.Serializer):

    name = serializers.CharField()
    id = serializers.CharField()
    created_by = UserSerializerMinimal(read_only=True)
    
    class Meta:
        model = BaseModel
        fields = ["id", "name"]


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


class SchemaSerializer(BaseModelSerializer, serializers.ModelSerializer):

    class Meta:
        model = Schema
        fields = "__all__"

class FacilitySerializerMinimal(serializers.ModelSerializer):
    class Meta:
        model = Facility
        fields = BaseModelSerializer.Meta.fields + ["abbreviation"]

class ProjectResponseSerializer(BaseModelSerializer, serializers.ModelSerializer):
    facility = FacilitySerializerMinimal(read_only=True)
    default_dataset_schema = BaseModelSerializer(read_only=True)
    project_schema = BaseModelSerializer(read_only=True)

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


class DatasetResponseSerializer(BaseModelSerializer, serializers.ModelSerializer):
    project = BaseModelSerializer(read_only=True)
    dataset_schema = BaseModelSerializer(read_only=True)
    created_by = UserSerializerMinimal(read_only=True)
    modified_by = UserSerializerMinimal(read_only=True)

    class Meta:
        model = Dataset
        fields = "__all__"
    
class DatasetSerializer(serializers.ModelSerializer):

    class Meta:
        model = Dataset
        fields = "__all__"

    def to_representation(self, data):
        return DatasetResponseSerializer(context=self.context).to_representation(data)