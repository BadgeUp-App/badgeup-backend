from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("achievements", "0004_usersticker_validation_score"),
    ]

    operations = [
        migrations.AddField(
            model_name="usersticker",
            name="detected_generation",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="usersticker",
            name="detected_make",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="usersticker",
            name="detected_model",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="usersticker",
            name="detected_year_range",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="usersticker",
            name="fun_fact",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="usersticker",
            name="location_label",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="usersticker",
            name="unlocked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="usersticker",
            name="unlocked_photo",
            field=models.ImageField(blank=True, null=True, upload_to="user_stickers/"),
        ),
        migrations.AddField(
            model_name="usersticker",
            name="user_message",
            field=models.TextField(blank=True),
        ),
    ]
