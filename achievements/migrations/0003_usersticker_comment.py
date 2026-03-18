from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("achievements", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="usersticker",
            name="comment",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
