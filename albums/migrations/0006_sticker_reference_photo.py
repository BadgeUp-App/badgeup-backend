from django.db import migrations, models
import albums.models


class Migration(migrations.Migration):

    dependencies = [
        ('albums', '0005_album_tags'),
    ]

    operations = [
        migrations.AddField(
            model_name='sticker',
            name='reference_photo',
            field=models.ImageField(
                blank=True,
                max_length=255,
                null=True,
                upload_to=albums.models.sticker_ref_photo_upload,
            ),
        ),
    ]
