from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_user_fcm_token"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_premium",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="premium_until",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
