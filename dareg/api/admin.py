from django.contrib import admin
from .models import (
    Facility,
    Project,
    Dataset,
    Schema,
    Language,
    UserProfile,
)

admin.site.register(Facility)
admin.site.register(Project)
admin.site.register(Dataset)
admin.site.register(Schema)
admin.site.register(Language)
admin.site.register(UserProfile)
