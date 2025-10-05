# Generated manually to rename input_params to app_config

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0020_add_output_resource_fields'),
    ]

    operations = [
        migrations.RenameField(
            model_name='job',
            old_name='input_params',
            new_name='app_config',
        ),
    ]
