# -*- coding: utf-8 -*-
# Generated by Django 1.11.7 on 2017-11-20 20:03
from __future__ import unicode_literals

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("msgs", "0057_auto_20170718_1504")]

    operations = [
        migrations.AlterField(
            model_name="message",
            name="modified_on",
            field=models.DateTimeField(
                default=django.utils.timezone.now, help_text="When message was last modified", null=True
            ),
        )
    ]
