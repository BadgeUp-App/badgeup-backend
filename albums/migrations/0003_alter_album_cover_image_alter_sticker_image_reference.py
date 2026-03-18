from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("albums", "0002_sticker_rarity"),
    ]

    operations = [
        migrations.AlterField(
            model_name="album",
            name="cover_image",
            field=models.ImageField(blank=True, max_length=255, null=True, upload_to="albums/covers/"),
        ),
        migrations.AlterField(
            model_name="sticker",
            name="image_reference",
            field=models.ImageField(blank=True, max_length=255, null=True, upload_to="stickers/reference/"),
        ),
    ]
