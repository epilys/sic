# Generated by Django 3.1.3 on 2021-07-07 11:14

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sic", "0027_auto_20210707_0810"),
    ]

    operations = [
        migrations.AddField(
            model_name="story",
            name="publish_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]
