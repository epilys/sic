# Generated by Django 3.1.3 on 2021-07-09 19:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sic", "0032_auto_20210709_1729"),
    ]

    operations = [
        migrations.AlterField(
            model_name="story",
            name="kind",
            field=models.ManyToManyField(related_name="stories", to="sic.StoryKind"),
        ),
        migrations.AlterField(
            model_name="tag",
            name="hex_color",
            field=models.CharField(
                blank=True, default="#ffffff", max_length=7, null=True
            ),
        ),
        migrations.AlterField(
            model_name="tag",
            name="parents",
            field=models.ManyToManyField(
                blank=True, related_name="children", to="sic.Tag"
            ),
        ),
    ]
