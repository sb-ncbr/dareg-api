from django.contrib import admin
from .models import (
    Facility,
    Project,
    Dataset,
    Schema,
    Language,
    UserProfile
)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'facility', 'created_by')

class DatasetAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'created_by')

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.select_related('project', 'created_by')
        return queryset

admin.site.register(Project, ProjectAdmin)
admin.site.register(Dataset, DatasetAdmin)

admin.site.register(Facility)
admin.site.register(Schema)
admin.site.register(Language)
admin.site.register(UserProfile)