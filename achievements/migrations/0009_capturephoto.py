from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("achievements", "0008_chatmessage"),
    ]

    operations = [
        migrations.CreateModel(
            name="CapturePhoto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("photo", models.ImageField(upload_to="capture_photos/")),
                ("captured_at", models.DateTimeField(auto_now_add=True)),
                ("location_lat", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ("location_lng", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                (
                    "user_sticker",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="capture_photos",
                        to="achievements.usersticker",
                    ),
                ),
            ],
            options={
                "ordering": ["-captured_at"],
            },
        ),
    ]
