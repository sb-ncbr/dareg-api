from django.contrib import admin
from .models import (
    Facility,
    Project,
    Dataset,
    Schema,
    Metadata,
    Language,
    UserProfile,
)

admin.site.register(Facility)
admin.site.register(Project)
admin.site.register(Dataset)
admin.site.register(Schema)
admin.site.register(Metadata)
admin.site.register(Language)
admin.site.register(UserProfile)
