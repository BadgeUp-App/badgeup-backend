from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("albums", "0008_album_custom_prompt_and_more"),
        ("users", "0004_user_premium_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ScanQuotaUsage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("count", models.PositiveIntegerField(default=0)),
                ("last_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="scan_quotas",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-date"],
                "unique_together": {("user", "date")},
            },
        ),
        migrations.AddIndex(
            model_name="scanquotausage",
            index=models.Index(fields=["user", "date"], name="albums_scan_user_id_date_idx"),
        ),
    ]
