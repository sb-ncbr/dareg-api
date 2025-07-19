from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0016_dataset_onedata_space_id'),
    ]

    operations = [
        TrigramExtension(),
    ]