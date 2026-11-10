from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0019_userprofile_onedata_last_sync'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='onedata_linked_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
