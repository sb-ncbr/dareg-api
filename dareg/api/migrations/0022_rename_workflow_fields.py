# Generated manually for renaming workflow fields

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0021_workflowtemplate_workflow_type'),
    ]

    operations = [
        migrations.RenameField(
            model_name='workflowtemplate',
            old_name='workflow_id',
            new_name='onedata_workflow_id',
        ),
        migrations.RenameField(
            model_name='job',
            old_name='workflow_id',
            new_name='onedata_workflow_id',
        ),
        migrations.RenameField(
            model_name='job',
            old_name='workflow_execution_id',
            new_name='onedata_workflow_execution_id',
        ),
    ]