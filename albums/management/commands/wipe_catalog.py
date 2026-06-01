from django.core.management.base import BaseCommand
from django.db import transaction

from albums.models import Album, ScanLog, Sticker, StickerReferencePhoto
from achievements.models import CapturePhoto, UserSticker


class Command(BaseCommand):
    help = (
        "Borra TODO el catalogo (albums, stickers, user stickers, capturas, scan logs) "
        "y sus archivos en storage. Dry-run por default; usar --confirm para ejecutar."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Ejecuta el borrado real. Sin esta flag solo reporta que se borraria.",
        )
        parser.add_argument(
            "--keep-files",
            action="store_true",
            help="Borra los rows pero deja los archivos en storage.",
        )

    def handle(self, *args, **options):
        confirm = options.get("confirm", False)
        keep_files = options.get("keep_files", False)

        counts = {
            "albums": Album.objects.count(),
            "stickers": Sticker.objects.count(),
            "reference_photos": StickerReferencePhoto.objects.count(),
            "user_stickers": UserSticker.objects.count(),
            "capture_photos": CapturePhoto.objects.count(),
            "scan_logs": ScanLog.objects.count(),
        }

        self.stdout.write("Catalogo actual:")
        for name, n in counts.items():
            self.stdout.write(f"  {name}: {n}")

        if not confirm:
            self.stdout.write(
                self.style.WARNING(
                    "DRY-RUN: nada borrado. Corre con --confirm para ejecutar."
                )
            )
            return

        deleted_files = 0
        if not keep_files:
            deleted_files = self._delete_storage_files()

        with transaction.atomic():
            ScanLog.objects.all().delete()
            CapturePhoto.objects.all().delete()
            UserSticker.objects.all().delete()
            StickerReferencePhoto.objects.all().delete()
            Sticker.objects.all().delete()
            Album.objects.all().delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Borrado completo. Archivos en storage eliminados: {deleted_files}."
            )
        )

    def _delete_storage_files(self) -> int:
        deleted = 0
        field_sources = [
            (Album.objects.all(), ["cover_image"]),
            (Sticker.objects.all(), ["image_reference", "reference_photo"]),
            (StickerReferencePhoto.objects.all(), ["photo"]),
            (UserSticker.objects.all(), ["photo", "unlocked_photo"]),
            (CapturePhoto.objects.all(), ["photo"]),
            (ScanLog.objects.all(), ["photo"]),
        ]
        for qs, fields in field_sources:
            for obj in qs.iterator():
                for field in fields:
                    f = getattr(obj, field, None)
                    if f and f.name:
                        try:
                            f.delete(save=False)
                            deleted += 1
                        except Exception:
                            self.stderr.write(
                                f"  no se pudo borrar archivo {field} de {obj.pk}"
                            )
        return deleted
