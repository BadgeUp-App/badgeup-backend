from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("achievements", "0005_usersticker_extra_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="usersticker",
            name="location_lat",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name="usersticker",
            name="location_lng",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
    ]
