from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from achievements.utils import compute_user_points

User = get_user_model()


class Command(BaseCommand):
    help = "Sincroniza User.points con los UserSticker aprobados existentes"

    def handle(self, *args, **options):
        users = User.objects.all()
        count = 0
        total_users = users.count()
        self.stdout.write(f"Sincronizando puntos para {total_users} usuarios...")
        for user in users:
            computed = compute_user_points(user)
            if user.points != computed:
                old_points = user.points
                user.points = computed
                user.save(update_fields=["points"])
                count += 1
                self.stdout.write(f"{user.username}: {old_points} -> {computed} pts")
        self.stdout.write(self.style.SUCCESS(f"Sincronizados {count} de {total_users} usuarios"))
