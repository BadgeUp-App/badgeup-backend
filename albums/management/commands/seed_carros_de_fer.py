from django.core.management.base import BaseCommand
from django.db import transaction

from albums.models import Album, Sticker


RARITY_POINTS = {
    "common": 10,
    "rare": 25,
    "epic": 50,
    "legendary": 100,
}

STICKERS = [
    {
        "name": "Toyota Tacoma TRD Off Road 2026",
        "description": "Pickup todoterreno con suspension FOX y modo crawl control.",
        "rarity": "epic",
    },
    {
        "name": "Ford Mustang Shelby GT350 2015",
        "description": "V8 5.2L Voodoo de 526 hp con escape de titanio.",
        "rarity": "legendary",
    },
    {
        "name": "Dodge Challenger SRT Hellcat 2019",
        "description": "Muscle car con V8 supercargado de 717 hp.",
        "rarity": "legendary",
    },
    {
        "name": "Chevrolet Chevy Pop 2005",
        "description": "Hatchback economico, clasico urbano mexicano.",
        "rarity": "common",
    },
    {
        "name": "Ford Fiesta ST 2016 Hatchback",
        "description": "Hot hatch turbo de 197 hp con chasis afilado.",
        "rarity": "rare",
    },
    {
        "name": "Ford Fiesta Sedan 2016",
        "description": "Compacto familiar, version sedan de la linea Fiesta.",
        "rarity": "common",
    },
    {
        "name": "Valiant Duster 1972",
        "description": "Muscle car mexicano con slant-six y linea fastback.",
        "rarity": "legendary",
    },
    {
        "name": "Dodge Charger V6 2016",
        "description": "Sedan musculoso con Pentastar de 3.6L.",
        "rarity": "rare",
    },
    {
        "name": "Ford F-150 Raptor 2019",
        "description": "Pickup de alto desempeno con V6 biturbo de 450 hp.",
        "rarity": "epic",
    },
    {
        "name": "Nissan Tsuru 2008",
        "description": "Sedan legendario, taxi y coche de calle por excelencia.",
        "rarity": "common",
    },
    {
        "name": "Kawasaki Ninja 500 2024",
        "description": "Supersport media cilindrada con motor paralelo de 451cc.",
        "rarity": "epic",
    },
]


class Command(BaseCommand):
    help = "Crea el album 'Carros de Fer' con 11 stickers de coleccion personal."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Borra el album y sus stickers si ya existe antes de crearlos.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        title = "Carros de Fer"
        reset = options.get("reset", False)

        existing = Album.objects.filter(title=title).first()
        if existing and reset:
            self.stdout.write(self.style.WARNING(f"Eliminando album existente: {title}"))
            existing.delete()
            existing = None

        if existing:
            album = existing
            self.stdout.write(self.style.WARNING(
                f"Album '{title}' ya existe (id={album.id}). Solo se crearan stickers faltantes."
            ))
        else:
            album = Album.objects.create(
                title=title,
                description="Coleccion personal de Fernando: pickups, muscle cars, compactos y una moto.",
                theme="Personal",
                tags="fer,carros,muscle,pickup,moto",
                is_premium=False,
            )
            self.stdout.write(self.style.SUCCESS(f"Album creado (id={album.id})."))

        created = 0
        skipped = 0
        for idx, data in enumerate(STICKERS, start=1):
            sticker, was_created = Sticker.objects.get_or_create(
                album=album,
                name=data["name"],
                defaults={
                    "description": data["description"],
                    "rarity": data["rarity"],
                    "reward_points": RARITY_POINTS[data["rarity"]],
                    "order": idx,
                },
            )
            if was_created:
                created += 1
                self.stdout.write(f"  + {sticker.order:02d} {sticker.name} [{sticker.rarity}]")
            else:
                skipped += 1
                self.stdout.write(f"  = {sticker.order:02d} {sticker.name} (ya existia)")

        self.stdout.write(self.style.SUCCESS(
            f"Listo. Creados: {created}, existentes: {skipped}, total: {album.stickers.count()}"
        ))
