# Generated by Django 4.2.17 on 2024-12-06 22:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("webui", "0006_alter_breachedcredential_file"),
    ]

    operations = [
        migrations.AlterField(
            model_name="breachedcredential",
            name="file",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]