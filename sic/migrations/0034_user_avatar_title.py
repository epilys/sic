# Generated by Django 3.1.3 on 2021-07-10 11:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sic", "0033_auto_20210709_1959"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="avatar_title",
            field=models.CharField(blank=True, max_length=256, null=True),
        ),
    ]
