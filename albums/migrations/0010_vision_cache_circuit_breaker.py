from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("albums", "0009_scanquotausage"),
    ]

    operations = [
        migrations.CreateModel(
            name="VisionResultCache",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phash", models.CharField(max_length=32, unique=True)),
                ("result_json", models.JSONField()),
                ("hit_count", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_hit_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-last_hit_at"],
            },
        ),
        migrations.AddIndex(
            model_name="visionresultcache",
            index=models.Index(fields=["phash"], name="albums_visi_phash_idx"),
        ),
        migrations.CreateModel(
            name="DailyAICost",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(unique=True)),
                ("total_usd", models.DecimalField(decimal_places=4, default=0, max_digits=10)),
                ("call_count", models.PositiveIntegerField(default=0)),
                ("prefilter_count", models.PositiveIntegerField(default=0)),
                ("cache_hit_count", models.PositiveIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-date"],
            },
        ),
    ]
