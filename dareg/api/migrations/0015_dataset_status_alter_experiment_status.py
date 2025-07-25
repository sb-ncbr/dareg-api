# Generated by Django 4.2.19 on 2025-02-23 10:47

import api.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0014_dataset_reservationid_facility_logo_experiment_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='dataset',
            name='status',
            field=models.CharField(choices=[('new', 'NEW'), ('finished', 'FINISHED')], default=api.models.DatasetStatus['NEW'], max_length=20),
        ),
        migrations.AlterField(
            model_name='experiment',
            name='status',
            field=models.CharField(choices=[('new', 'NEW'), ('prepared', 'PREPARED'), ('running', 'RUNNING'), ('synchronizing', 'SYNCHRONIZING'), ('success', 'SUCCESS'), ('failure', 'FAILURE'), ('discarded', 'DISCARDED')], default=api.models.ExperimentStatus['NEW'], max_length=20),
        ),
    ]
