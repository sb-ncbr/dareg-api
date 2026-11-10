from django.conf import settings
from django.contrib.auth.models import User, Group
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.fields import SerializerMethodField
from jsonschema import Draft7Validator, SchemaError

from .models import Facility, Job, Project, Dataset, Schema, BaseModel, PermsGroup, UserProfile, Instrument, Experiment, \
    ExperimentStatus, WorkflowTemplate
from .onboarding import onedata_access_allowed

# Managed by the Onedata reconciler (onedata_api/sync.py), never writable through the API
ONEDATA_SYNC_FIELDS = ["onedata_group_id", "onedata_sync_status", "onedata_sync_error", "onedata_synced_at"]


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
                        "last_login": x.last_login,
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
    onedata_auto_link_enabled = serializers.SerializerMethodField()
    onedata_required = serializers.SerializerMethodField()
    is_superuser = serializers.SerializerMethodField()
    onedata_access_allowed = serializers.SerializerMethodField()

    def get_onedata_auto_link_enabled(self, obj) -> bool:
        return settings.ONEDATA_AUTO_LINK_ENABLED

    def get_onedata_required(self, obj) -> bool:
        return settings.ONEDATA_REQUIRED

    def get_is_superuser(self, obj) -> bool:
        return obj.user.is_superuser

    def get_onedata_access_allowed(self, obj) -> bool:
        return onedata_access_allowed(obj.user)

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
        fields = ["created", "default_data_rows", "any_datasets", "any_facilities", "any_projects", "app_version", "avatar", "last_login", "default_theme", "default_lang",
                  "onedata_user_id", "onedata_last_sync_at", "onedata_last_sync_error", "onedata_auto_link_enabled",
                  "onedata_required", "onedata_linked_at", "is_superuser", "onedata_access_allowed"]
        read_only_fields = ["onedata_user_id", "onedata_last_sync_at", "onedata_last_sync_error", "onedata_linked_at"]


# INVITE-MODE (disabled, replaced by auto-link)
# class OnedataLinkSerializer(serializers.Serializer):
#     token = serializers.CharField(write_only=True)


# INVITE-MODE (disabled, replaced by auto-link)
# class OnedataLinkResponseSerializer(serializers.Serializer):
#     onedata_user_id = serializers.CharField()
#     joined_groups = serializers.ListField(child=serializers.CharField())
#     failed_groups = serializers.ListField(child=serializers.DictField())


class OnedataSyncRequestSerializer(serializers.Serializer):
    force = serializers.BooleanField(required=False, default=False)
    dry_run = serializers.BooleanField(required=False, default=False)


class FailedGroupSerializer(serializers.Serializer):
    group_id = serializers.CharField()
    error = serializers.CharField()


class OnedataSyncResponseSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    skipped = serializers.BooleanField()
    onedata_user_id = serializers.CharField(allow_blank=True)
    onedata_last_sync_at = serializers.DateTimeField(allow_null=True)
    onedata_last_sync_error = serializers.CharField(allow_blank=True)
    joined_groups = serializers.ListField(child=serializers.CharField())
    failed_groups = FailedGroupSerializer(many=True)
    error = serializers.CharField(allow_null=True)
    reason = serializers.ChoiceField(
        choices=["auto_link_disabled", "not_oidc", "busy", "no_onedata_account", "onedata_unavailable"],
        allow_null=True,
    )
    found_onedata_user_id = serializers.CharField(allow_blank=True)


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ["name"]


class FacilitySerializer(serializers.ModelSerializer, PermsModelSerializer):
    class Meta:
        model = Facility
        fields = "__all__"
        read_only_fields = ["created_by", "modified_by", "onedata_staff_group_id", "onedata_user_id"] + ONEDATA_SYNC_FIELDS
    
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
        fields = BaseModelSerializer.Meta.fields + ["abbreviation", "email", "web", "logo"]

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
        read_only_fields = ["id", "created_by", "modified_by", "onedata_managers_group_id"] + ONEDATA_SYNC_FIELDS

    def to_representation(self, data):
        """Serialize the facility as a nested object."""
        return ProjectResponseSerializer(context=self.context).to_representation(data)

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user

        return Project.objects.create(**validated_data)


class ExperimentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Experiment
        fields = "__all__"
        read_only_fields = ["id", "created_by", "modified_by"]

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user

        return Experiment.objects.create(**validated_data)


class DatasetResponseSerializer(BaseModelSerializer, serializers.ModelSerializer, PermsModelSerializer):
    project = BaseModelSerializer(read_only=True)
    experiments = SerializerMethodField()
    dataset_schema = BaseModelSerializer(read_only=True)
    created_by = UserSerializerMinimal(read_only=True)
    modified_by = UserSerializerMinimal(read_only=True)

    @extend_schema_field(ExperimentSerializer(many=True))
    def get_experiments(self, obj):
        return ExperimentSerializer(obj.experiment_set.exclude(status=ExperimentStatus.DISCARDED).order_by('created'), many=True, required=True).data

    onedata_visit_id = serializers.SerializerMethodField(source='onedata_visit_id')

    def get_onedata_visit_id(self, obj):
        return obj.onedata_visit_id

    onedata_url = serializers.SerializerMethodField()

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_onedata_url(self, obj):
        from onedata_api.onezone import onedata_gui_url
        return onedata_gui_url(obj)
    
    class Meta:
        model = Dataset
        fields = "__all__"
    
class DatasetSerializer(serializers.ModelSerializer):

    class Meta:
        model = Dataset
        fields = "__all__"
        read_only_fields = ["id", "created_by", "modified_by", "onedata_acl_hash"] + ONEDATA_SYNC_FIELDS

    def to_representation(self, data):
        return DatasetResponseSerializer(context=self.context).to_representation(data)

    def validate(self, attrs):
        """Validate metadata against the selected dataset schema."""
        
        # getting schema submitted by dataset request
        schema = attrs.get("schema")

        # if schema not present, use already existing schema assigned to dataset
        if schema is None and self.instance is not None:
            schema = self.instance.schema

        # allowing datasets without schema
        if schema is None:
            return attrs

        # skipping validation when metadata was not changed
        if "metadata" not in attrs and self.instance is not None:
            return attrs

        metadata = attrs.get("metadata", {})
        try:
            validator = Draft7Validator(schema.schema)
            validation_errors = sorted(
                validator.iter_errors(metadata),
                key=lambda error: list(error.path),
            )
        except SchemaError as error:
            raise serializers.ValidationError({
                "schema": f"The selected schema is invalid: {error.message}"
            })

        if validation_errors:
            raise serializers.ValidationError({
                "metadata": [error.message for error in validation_errors]
            })

        return attrs
    
    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user

        return Dataset.objects.create(**validated_data)


class ReservationSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    from_date = serializers.DateTimeField()
    to_date = serializers.DateTimeField()
    user = serializers.CharField()
    description = serializers.CharField()
    project_id = serializers.CharField()
    dataset_status = SerializerMethodField()

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_dataset_status(self, obj):
        dataset = Dataset.objects.filter(reservationId=obj["id"]).first()
        return dataset.status if dataset else None

class InstrumentSerializer(serializers.ModelSerializer):
    facility = FacilitySerializerMinimal(read_only=True)
    class Meta:
        model = Instrument
        fields = ["id", "name", "support", "contact", "method", "facility", "default_data_dir"]


class TempTokenSerializer(serializers.Serializer):
    token = serializers.CharField()
    provider_url = serializers.CharField()
    one_data_directory_id = serializers.CharField()

class WorkflowTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowTemplate
        fields = "__all__"
        read_only_fields = ["id", "created_by", "modified_by"]

    def validate(self, attrs):
        # Create a temporary instance to trigger model validation
        instance = WorkflowTemplate(**attrs)
        instance.clean()
        return attrs

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user

        return WorkflowTemplate.objects.create(**validated_data)
    
class JobSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = [
            'created', 'modified', 'id', 'created_by', 'modified_by',
            'workflow_template', 'root_resource_content_type', 'root_resource_id',
            'output_resource_content_type', 'output_resource_id',
            'name', 'description', 'status',
            'app_config', 'start_time', 'end_time', 'log_level'
        ]
        read_only_fields = ["id", "created_by", "modified_by"]

    def validate(self, attrs):
        from onedata_api.middleware import verify_job

        # Create a temporary instance to trigger model validation
        instance = Job(**attrs)
        instance.clean()

        # Verify job runtime requirements before saving
        try:
            verify_job(instance)
        except ValueError as e:
            raise serializers.ValidationError({"app_config": str(e)})

        return attrs

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user

        return Job.objects.create(**validated_data)
