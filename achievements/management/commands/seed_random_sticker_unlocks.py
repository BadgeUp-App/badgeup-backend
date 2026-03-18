import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import F
from django.utils import timezone

from achievements.models import UserSticker
from albums.models import Sticker
from users.models import User


LAND_COORDS = [
    (40.7128, -74.006),    # New York
    (34.0522, -118.2437),  # Los Angeles
    (19.4326, -99.1332),   # CDMX
    (-23.5505, -46.6333),  # São Paulo
    (51.5074, -0.1278),    # London
    (48.8566, 2.3522),     # Paris
    (40.4168, -3.7038),    # Madrid
    (52.52, 13.405),       # Berlin
    (41.9028, 12.4964),    # Rome
    (37.7749, -122.4194),  # San Francisco
    (35.6762, 139.6503),   # Tokyo
    (1.3521, 103.8198),    # Singapore
    (28.6139, 77.209),     # New Delhi
    (-33.8688, 151.2093),  # Sydney
    (-34.6037, -58.3816),  # Buenos Aires
    (-1.2921, 36.8219),    # Nairobi
    (6.5244, 3.3792),      # Lagos
    (30.0444, 31.2357),    # Cairo
    (25.276987, 55.296249),# Dubai
    (55.7558, 37.6173),    # Moscow
    (45.4642, 9.19),       # Milan
    (59.3293, 18.0686),    # Stockholm
    (50.1109, 8.6821),     # Frankfurt
    (-17.8249, 31.053),    # Harare
    (-26.2041, 28.0473),   # Johannesburg
]


def pick_land_coords():
    lat, lng = random.choice(LAND_COORDS)
    lat += random.uniform(-0.35, 0.35)
    lng += random.uniform(-0.35, 0.35)
    return round(lat, 6), round(lng, 6)


class Command(BaseCommand):
    help = "Create random sticker unlocks with locations for existing users"

    def add_arguments(self, parser):
        parser.add_argument("--per-user", type=int, default=4)
        parser.add_argument("--users", nargs="*", help="Usernames to seed")
        parser.add_argument("--purge", action="store_true", help="Delete all user stickers before seeding")

    def handle(self, *args, **options):
        per_user = int(options.get("per_user") or 4)
        usernames = options.get("users") or []
        purge = bool(options.get("purge"))

        if purge:
            deleted, _ = UserSticker.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Purged {deleted} user stickers"))

        users_qs = User.objects.all()
        if usernames:
            users_qs = users_qs.filter(username__in=usernames)
        else:
            users_qs = users_qs.exclude(is_staff=True).exclude(is_superuser=True)
        users = list(users_qs)
        stickers = list(Sticker.objects.all())
        if not users or not stickers:
            self.stdout.write(self.style.WARNING("No users or stickers found"))
            return
        total_created = 0
        for user in users:
            existing_ids = set(
                UserSticker.objects.filter(user=user).values_list("sticker_id", flat=True)
            )
            available = [s for s in stickers if s.id not in existing_ids]
            if not available:
                continue
            sample = random.sample(available, min(per_user, len(available)))
            for sticker in sample:
                lat, lng = pick_land_coords()
                unlocked_at = timezone.now() - timedelta(
                    days=random.randint(0, 60),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59),
                )
                user_sticker, created = UserSticker.objects.update_or_create(
                    user=user,
                    sticker=sticker,
                    defaults={
                        "status": UserSticker.STATUS_APPROVED,
                        "validated": True,
                        "validated_at": unlocked_at,
                        "unlocked_at": unlocked_at,
                        "validation_score": 0.95,
                        "location_lat": lat,
                        "location_lng": lng,
                    },
                )
                if created:
                    type(user).objects.filter(pk=user.id).update(points=F("points") + sticker.reward_points)
                    total_created += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {total_created} unlocks"))
