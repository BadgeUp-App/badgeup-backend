from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("albums", "0006_sticker_reference_photo"),
    ]

    operations = [
        migrations.CreateModel(
            name="StickerReferencePhoto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("photo", models.ImageField(max_length=255, upload_to="stickers/refs/")),
                ("label", models.CharField(blank=True, max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("sticker", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reference_photos", to="albums.sticker")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
