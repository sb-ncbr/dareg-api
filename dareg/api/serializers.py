from django.contrib.auth.models import User, Group
from rest_framework import serializers
from .models import Facility, Project, Dataset, Schema, BaseModel, PermsGroup, UserProfile

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
        read_only_fields = ["id", "created_by", "modified_by"]
    
class PermsModelSerializer(serializers.Serializer):

    perms = serializers.SerializerMethodField()
    shares = serializers.SerializerMethodField()

    def get_perms(self, obj):
        return obj.max_perm(self.context['request'])
    
    def get_shares(self, obj):
        shares = []

        for level in ["owner", "editor", "viewer"]:

            try:
                group = PermsGroup.objects.get(name=f"{obj.id}_{level}")
                for x in group.user_set.all():
                    shares.append({
                        "id": x.id,
                        "name": '{} {}'.format(x.first_name, x.last_name),
                        "perms": level,
                    })
            except PermsGroup.DoesNotExist:
                print(f"Group {level} does not exist for {obj}", flush=True)

        return shares


class UserSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    def get_name(self, obj):
        return '{} {}'.format(obj.first_name, obj.last_name)

    class Meta:
        model = User
        fields = ["id", "username", "email", "groups", "first_name", "last_name", "name"]


class ProfileSerializer(serializers.ModelSerializer):
    any_facilities = serializers.SerializerMethodField()
    any_projects = serializers.SerializerMethodField()
    any_datasets = serializers.SerializerMethodField()

    def get_any_facilities(self, obj):
        for x in Facility.objects.all():
            if x.perm_atleast(self.context['request'], PermsGroup.VIEWER):
                return True
        return False
    
    def get_any_projects(self, obj):
        for x in Project.objects.all():
            if x.perm_atleast(self.context['request'], PermsGroup.VIEWER):
                return True
        return False

    def get_any_datasets(self, obj):
        for x in Dataset.objects.all():
            if x.perm_atleast(self.context['request'], PermsGroup.VIEWER):
                return True
        return False

    class Meta:
        model = UserProfile
        fields = ["created", "default_data_rows", "any_datasets", "any_facilities", "any_projects", "app_version", "avatar", "last_login"]


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ["name"]


class FacilitySerializer(serializers.ModelSerializer, PermsModelSerializer):
    class Meta:
        model = Facility
        fields = "__all__"
        read_only_fields = ["created_by", "modified_by"]
    
    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user

        return Facility.objects.create(**validated_data)


class SchemaSerializer(serializers.ModelSerializer):

    class Meta:
        model = Schema
        fields = "__all__"
        read_only_fields = ["id", "created_by", "modified_by"]

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user

        return Schema.objects.create(**validated_data)

class FacilitySerializerMinimal(serializers.ModelSerializer):
    class Meta:
        model = Facility
        fields = BaseModelSerializer.Meta.fields + ["abbreviation"]

class ProjectResponseSerializer(BaseModelSerializer, serializers.ModelSerializer, PermsModelSerializer):
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
        read_only_fields = ["id", "created_by", "modified_by"]

    def to_representation(self, data):
        """Serialize the facility as a nested object."""
        return ProjectResponseSerializer(context=self.context).to_representation(data)

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user

        return Project.objects.create(**validated_data)


class DatasetResponseSerializer(BaseModelSerializer, serializers.ModelSerializer, PermsModelSerializer):
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
        read_only_fields = ["id", "created_by", "modified_by"]

    def to_representation(self, data):
        return DatasetResponseSerializer(context=self.context).to_representation(data)
    
    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user

        return Dataset.objects.create(**validated_data)

