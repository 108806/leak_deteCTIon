# Generated by Django 4.2.19 on 2025-02-23 18:23

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("webui", "0002_alter_scrapfile_size"),
    ]

    operations = [
        migrations.AddField(
            model_name="scrapfile",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name="breachedcredential",
            name="file",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="breached_credentials",
                to="webui.scrapfile",
            ),
        ),
        migrations.AlterField(
            model_name="breachedcredential",
            name="string",
            field=models.CharField(db_index=True, max_length=1024),
        ),
        migrations.AlterField(
            model_name="scrapfile",
            name="name",
            field=models.CharField(db_index=True, max_length=256),
        ),
        migrations.AlterField(
            model_name="scrapfile",
            name="sha256",
            field=models.CharField(
                default="", editable=False, max_length=64, unique=True
            ),
        ),
        migrations.AlterField(
            model_name="scrapfile",
            name="size",
            field=models.DecimalField(
                decimal_places=2,
                default=0.0,
                help_text="Size of the file in MB",
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(0.0)],
            ),
        ),
        migrations.AddIndex(
            model_name="breachedcredential",
            index=models.Index(fields=["string"], name="webui_breac_string_63808b_idx"),
        ),
    ]
