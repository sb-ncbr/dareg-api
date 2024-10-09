from collections.abc import Callable, Sequence
from typing import Any
from django.contrib import admin

from django.urls import reverse
from onedata_wrapper.models.filesystem.entry_request import EntryRequest

from .models import (
    Facility,
    PermsGroup,
    Project,
    Dataset,
    Schema,
    Language,
    UserProfile
)
from onedata_api.middleware import create_new_dataset, create_public_share, establish_dataset
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.http import HttpRequest
from django.utils.html import format_html
from guardian.admin import GuardedModelAdmin

ONEZONE_HOST = 'onedata.e-infra.cz'

class BaseModelAdmin(GuardedModelAdmin, admin.ModelAdmin):

    def get_fieldsets(self, request, obj):
        fieldsets = super().get_fieldsets(request, obj)
        metadata_fields = ('created', 'modified', 'id', 'created_by', 'modified_by')
        for fieldset in fieldsets:
            fieldset[1]['fields'] = [field for field in fieldset[1]['fields'] if field not in metadata_fields]
        fieldsets.append(('Metadata', {'fields': metadata_fields, 'classes': ['']}))
        return fieldsets

    def get_readonly_fields(self, request, obj):
        return super().get_readonly_fields(request, obj) + ('created', 'modified', 'id')
    
    def get_list_display(self, request: HttpRequest) -> Sequence[str] | Callable:
        return super().get_list_display(request)
    
    readonly_fields = ('created', 'modified', 'id', 'created_by', 'modified_by')

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:
        if not change:
            obj.created_by = request.user
        obj.modified_by = request.user
        obj.save()
    
    list_display = ('created', 'modified', '_created_by', '_modified_by')

    def _get_admin_url(self, obj: Any) -> str:
        return reverse('admin:%s_%s_change' % (obj._meta.app_label, obj._meta.model_name), args=[obj.pk])
    
    def _user_to_str(self, user):
        if user is None:
            return 'None'
        name = user.userprofile.full_name if hasattr(user, 'userprofile') else user.username
        return format_html(f"<a href=\"{self._get_admin_url(user)}\">{name}</a>")

    @admin.display
    def _created_by(self, obj):
        return self._user_to_str(obj.created_by)
    
    @admin.display
    def _modified_by(self, obj):
        return self._user_to_str(obj.modified_by)

class ProjectAdminInline(admin.TabularInline):
    model = Project
    extra = 0

class DatasetAdminInline(admin.TabularInline):
    model = Dataset
    extra = 0
    fields = ('name', 'description')


class ProjectAdmin(BaseModelAdmin):
    list_display = ('name', 'facility', 'onedata_space_ids', 'created_by') + BaseModelAdmin.list_display
    search_fields = ('name', 'facility__name')
    list_filter = ('facility', 'default_dataset_schema')

    def onedata_space_ids(self, obj):
        return format_html(f"<a href=\"https://{ONEZONE_HOST}/ozw/onezone/i#/onedata/spaces/{obj.onedata_space_id}\">{obj.onedata_space_id}</a>")
    
    onedata_space_ids.short_description = 'OneData Space'

    inlines = [DatasetAdminInline]

class DatasetAdmin(BaseModelAdmin):
    list_display = ('name', 'project', 'onedata_share_link', 'onedata_link') + BaseModelAdmin.list_display
    search_fields = ('name', 'description')
    list_filter = ('project','project__facility', 'schema')

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.select_related('project', 'created_by')
        return queryset
    
    def onedata_link(self, obj):
        if obj.onedata_visit_id == "":
            return 'No visit folder'
        return format_html(f"<a href=\"https://{ONEZONE_HOST}/ozw/onezone/i#/onedata/spaces/{obj.project.onedata_space_id}/data?options=dir.{obj.onedata_visit_id.decode()}\">Visit folder {obj.name}</a>")
    onedata_link.short_description = 'OneData Folder'

    def onedata_share_link(self, obj):
        if obj.onedata_share_id == "":
            return 'No public share'
        return format_html(f"<a href=\"https://{ONEZONE_HOST}/share/{obj.onedata_share_id}\">Public share {obj.name}</a>")
    onedata_share_link.short_description = 'OneData Public Share'

    def create_onedata_share(self, request, queryset):
        for dataset in queryset:
            if dataset.onedata_share_id == "":
                if dataset.onedata_file_id == "":
                    self.message_user(request, f"Failed to create public share for {dataset}. Dataset doesn't have any supported space.", level='ERROR')
                    return
                print(f"Creating public share for {dataset}", flush=True)
                share, error = create_public_share(dataset.project, dataset.name, dataset.description, EntryRequest(file_id=dataset.onedata_file_id))
                if error is not None:
                    self.message_user(request, f"Failed to create public share for {dataset}. {error}", level='ERROR')
                    return
                if share.share_id is None:
                    self.message_user(request, f"Failed to create public share for {dataset}.", level='ERROR')
                    return
                dataset.onedata_share_id = share.share_id
                dataset.save()
                self.message_user(request, f"Public share for {dataset} created successfully.", level='SUCCESS')
            else:
                self.message_user(request, f"Public share for {dataset} already exists.", level='WARNING')
    create_onedata_share.short_description = 'Create OneData Share'

    def create_dataset(self, request, queryset):
        for dataset in queryset:
            if dataset.onedata_dataset_id == "":
                if dataset.onedata_file_id == "":
                    self.message_user(request, f"Failed to create dataset for {dataset}. Dataset doesn't have any directory.", level='ERROR')
                    return
                print(f"Creating dataset for {dataset}", flush=True)
                visit_id, error = establish_dataset(dataset.project, dataset.onedata_file_id)
                if error is not None:
                    self.message_user(request, f"Failed to create dataset for {dataset}. {error}", level='ERROR')
                    return
                if visit_id is None:
                    self.message_user(request, f"Failed to create dataset for {dataset}.", level='ERROR')
                    return
                dataset.onedata_dataset_id = visit_id
                dataset.save()
                self.message_user(request, f"Visit folder for {dataset} created successfully.", level='SUCCESS')
            else:
                self.message_user(request, f"Visit folder for {dataset} already exists.", level='WARNING')
    create_dataset.short_description = 'Create OneData Dataset'

    def create_onedata_folder(self, request, queryset):
        for dataset in queryset:
            if dataset.onedata_file_id == "":
                if dataset.onedata_space_id == "":
                    self.message_user(request, f"Failed to create visit folder for {dataset}. Dataset doesn't have any supported space.", level='ERROR')
                    return
                print(f"Creating visit folder for {dataset}", flush=True)
                folder, error = create_new_dataset(dataset.project, dataset.name)
                if error is not None:
                    self.message_user(request, f"Failed to create visit folder for {dataset}. {error}", level='ERROR')
                    return
                if folder is None:
                    self.message_user(request, f"Failed to create visit folder for {dataset}. Please contact the administrator of DAREG.", level='ERROR')
                    return
                dataset.onedata_file_id = folder.file_id
                dataset.save()
                self.message_user(request, f"Visit folder for {dataset} created successfully.", level='SUCCESS')
            else:
                self.message_user(request, f"Visit folder for {dataset} already exists.", level='WARNING')
    create_onedata_folder.short_description = 'Create OneData Folder'
    actions = ['create_onedata_share', 'create_dataset', 'create_onedata_folder']

class FacilityAdmin(BaseModelAdmin):
    list_display = ('name', 'abbreviation', 'has_onedata_token', 'has_onedata_provider') + BaseModelAdmin.list_display
    search_fields = ('name', 'abbreviation')
    inlines = [ProjectAdminInline]

    def has_onedata_token(self, obj):
        return obj.onedata_token is not None
    
    has_onedata_token.boolean = True
    has_onedata_token.short_description = 'OneData Token'
    
    def has_onedata_provider(self, obj):
        return obj.onedata_provider_url is not None
    
    has_onedata_provider.boolean = True
    has_onedata_provider.short_description = 'OneData Provider'

class SchemaAdmin(BaseModelAdmin):
    list_display = ('name', 'description', 'version') + BaseModelAdmin.list_display
    search_fields = ('name', 'description')
    list_filter = ('name',)

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    extra = 0
    fk_name = 'user'

class UserProfileAdmin(BaseModelAdmin):
    list_display = ('avatar', 'full_name', 'last_login') + BaseModelAdmin.list_display

    def avatar(self, obj):
        return format_html('<img src="{}" width="32px" style="background: #E3E3E3;padding: 1px;"/>'.format(obj.avatar))
    
    avatar.empty_value_display = 'No image'
    avatar.short_description = 'Image'

    # inlines = [UserInlines]

class UserAdmin(BaseUserAdmin):
    
    inlines = [UserProfileInline]

def _change_group_display_name(group: Group) -> str:
    try:
        g = PermsGroup.objects.get(id=group.id)
        return g.__str__()
    except PermsGroup.DoesNotExist:
        return group.__str__()

Group.__str__ = _change_group_display_name
    
admin.site.register(Project, ProjectAdmin)
admin.site.register(Dataset, DatasetAdmin)
admin.site.register(Facility, FacilityAdmin)
admin.site.register(Schema, SchemaAdmin)

admin.site.register(UserProfile, UserProfileAdmin)
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

admin.site.register(Language)
