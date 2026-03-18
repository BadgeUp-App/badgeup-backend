from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("achievements", "0003_usersticker_comment"),
    ]

    operations = [
        migrations.AddField(
            model_name="usersticker",
            name="validation_score",
            field=models.FloatField(blank=True, null=True),
        ),
    ]
