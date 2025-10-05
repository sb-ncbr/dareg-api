# Generated manually to remove unique constraint from onedata_workflow_id

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0021_rename_input_params_to_app_config'),
    ]

    operations = [
        migrations.AlterField(
            model_name='workflowtemplate',
            name='onedata_workflow_id',
            field=models.CharField(max_length=200, unique=False, verbose_name='Onedata Workflow ID'),
        ),
    ]
