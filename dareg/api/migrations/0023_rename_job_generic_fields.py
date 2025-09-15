# Generated manually for renaming Job generic foreign key fields

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0022_rename_workflow_fields'),
    ]

    operations = [
        migrations.RenameField(
            model_name='job',
            old_name='content_type',
            new_name='root_resource_content_type',
        ),
        migrations.RenameField(
            model_name='job',
            old_name='object_id',
            new_name='root_resource_id',
        ),
    ]