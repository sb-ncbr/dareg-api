# Generated manually on 2025-10-01

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('api', '0019_auto_20250928_1244'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='output_resource_content_type',
            field=models.ForeignKey(
                blank=True,
                help_text='Content type of the related object (Dataset or Experiment)',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='job_output_resource',
                to='contenttypes.contenttype',
            ),
        ),
        migrations.AddField(
            model_name='job',
            name='output_resource_id',
            field=models.UUIDField(
                blank=True,
                help_text='ID of the related object (Dataset or Experiment)',
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name='job',
            name='root_resource_content_type',
            field=models.ForeignKey(
                blank=True,
                help_text='Content type of the related object (Project, Dataset, or Experiment)',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='job_root_resource',
                to='contenttypes.contenttype',
            ),
        ),
    ]
