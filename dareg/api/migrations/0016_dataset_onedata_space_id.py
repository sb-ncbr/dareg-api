# Generated by Django 4.2.20 on 2025-04-04 13:12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0015_dataset_status_alter_experiment_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='dataset',
            name='onedata_space_id',
            field=models.CharField(blank=True, max_length=512, null=True, verbose_name='Onedata Space ID'),
        ),
    ]