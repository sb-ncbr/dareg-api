from django.contrib import admin
from .models import Facility, Project, Dataset, Template, FilledTemplate, Language, UserProfile

admin.site.register(Facility)
admin.site.register(Project)
admin.site.register(Dataset)
admin.site.register(Template)
admin.site.register(FilledTemplate)
admin.site.register(Language)
admin.site.register(UserProfile)
