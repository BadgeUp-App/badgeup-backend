# BadgeUp — Backend

API de la plataforma BadgeUp. Albumes coleccionables digitales, captura de fotos en campo, validacion con IA, gamificacion y geolocalizacion.

Backend en produccion: <https://badgeup-backend.onrender.com>

## Que hace

- Maneja usuarios, albumes y stickers con multiples tipos de raridad y sistema de puntos.
- Procesa fotos enviadas por la app: una sola foto puede desbloquear varios stickers a la vez (multi-unlock) cuando la imagen contiene varios elementos detectables.
- Usa OpenAI Vision (`gpt-4.1-mini`) para reconocer contenido y decidir matches contra los stickers de cada album.
- Valida ubicacion GPS por sticker cuando el album lo requiere.
- Soporta reconocimiento facial opcional para albumes de personas.
- Registra cada captura con metadatos (foto, lat/lng, fecha) para reconstruir un mapa personal por usuario.
- Expone endpoints para leaderboard global, historial de captura, scan logs y administracion de albums.

## Stack

- Django 4.2 + Django REST Framework 3.15
- PostgreSQL como base principal
- SimpleJWT para autenticacion
- Firebase Admin para login mobile (Google y email)
- OpenAI 1.45 (modelo `gpt-4.1-mini`)
- django-storages + boto3 contra Supabase S3 para imagenes
- Celery + Channels disponibles (queued, no activos en el plan actual)
- Despliegue en Render con Docker, Postgres externo y storage en Supabase

## Arquitectura

```
badgeup/         configuracion, settings env-driven, ASGI
users/           User custom (email unico, points, avatar), JWT, Google/Firebase, leaderboard
albums/          Album, Sticker, ScanLog, GlobalScanView (entrada principal de captura)
achievements/    UserSticker, CapturePhoto, services.analyze_photo_global con OpenAI
```

Optimizaciones aplicadas:

- Prefetch con `to_attr` y annotations en queries de listado para evitar N+1.
- Cache por instancia en serializers que dependen de `user_stickers`.
- `pagination_class = None` en endpoints donde el dataset esta naturalmente acotado (por ejemplo el mapa personal).
- Llamadas a notificaciones envueltas en try/except para tolerar la ausencia de Redis en el plan free.

## Flujo de captura

1. La app envia una foto a `POST /api/scan/`.
2. El backend pasa la imagen a `analyze_photo_global`, que arma un prompt con el catalogo de stickers candidatos del album seleccionado o de todos los albums activos.
3. La IA responde con un array `matches[]`.
4. Por cada match aprobado se crea un `UserSticker`, se sube la foto a Supabase S3 y se suman puntos.
5. La respuesta incluye `all_unlocked` y `unlock_count` para que el cliente muestre el resultado completo.

## Endpoints

Algunas rutas relevantes:

```
POST  /api/auth/register/
POST  /api/auth/login/
POST  /api/auth/google/mobile/
GET   /api/auth/profile/
GET   /api/auth/leaderboard/

GET   /api/albums/
GET   /api/albums/<id>/
POST  /api/albums/                   admin
POST  /api/stickers/                 admin

POST  /api/scan/                     captura principal con IA
GET   /api/scan-logs/                historial de scans
GET   /api/captures/history/         capturas aprobadas del usuario
GET   /api/stickers/locations/       pins del mapa personal
```

Todas las rutas (excepto registro, login y leaderboard) requieren `Authorization: Bearer <jwt>`.

## Estructura del repo

```
badgeup-backend/
├── badgeup/
├── users/
├── albums/
├── achievements/
├── render.yaml
├── Dockerfile
└── requirements.txt
```

## Cliente

El cliente oficial es la app mobile de BadgeUp en Flutter (iOS), repo aparte: <https://github.com/BadgeUp-App/badgeup-mobile>.
