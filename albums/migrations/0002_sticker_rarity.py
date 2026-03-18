from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("albums", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="sticker",
            name="rarity",
            field=models.CharField(blank=True, max_length=20),
        ),
    ]
