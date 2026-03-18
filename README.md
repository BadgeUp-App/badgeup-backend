# BadgeUp – Backend

Backend para la plataforma BadgeUp: álbumes coleccionables digitales, validación de fotos en campo y gamificación con puntos y logros. El proyecto usa Django, Django REST Framework y SimpleJWT para exponer la API, con PostgreSQL, Celery/Redis y servicios externos como OpenAI Vision.

## Características
- Autenticación con JWT (registro, login, perfil, leaderboard).
- Gestión de álbumes y stickers, con campos para ubicación y recompensa.
- Flujo de desbloqueo de stickers con subida de fotos y validación asíncrona vía Celery.
- Integración preparada para OpenAI Vision (modo simulación si no hay API key).
- Deploy y desarrollo con Docker + Docker Compose.

## Stack
- **Python 3.11 (Docker) / 3.9 local**
- Django 4.2, Django REST Framework, SimpleJWT
- PostgreSQL + Redis
- Celery 5
- AWS S3 (opcional) mediante django-storages
- OpenAI Python SDK

## Estructura principal
```
badgeup-backend/
├── badgeup/            # Configuración central, Celery, URLs
├── users/              # Modelo de usuario, registro, JWT, perfil
├── albums/             # Álbumes y stickers
├── achievements/       # Desbloqueo y validación de stickers
├── Dockerfile          # Imagen base del proyecto
├── docker-compose.yml  # Servicios web, postgres, redis, celery
├── requirements.txt
└── README.md
```

## Requisitos
- Docker y Docker Compose
- (Opcional) Python 3.9+ y virtualenv si quieres ejecutar sin Docker

## Configuración inicial
1. Copia el archivo de variables de entorno:
   ```bash
   cp .env.example .env
   ```
2. Ajusta valores sensibles (`DJANGO_SECRET_KEY`, claves de OpenAI, etc.).

### Variables clave
| Variable | Descripción |
| --- | --- |
| `DJANGO_SECRET_KEY` | Secreto de Django |
| `POSTGRES_*` | Configuración de base de datos |
| `CELERY_BROKER_URL` | Broker (por defecto Redis) |
| `USE_S3` + `AWS_*` | Habilita almacenamiento en S3 |
| `OPENAI_API_KEY` | Para validación de fotos (modo simulación si vacío) |

## Levantar con Docker
```bash
docker compose up --build
```
Servicios incluidos:
- `web`: aplicación Django (dev server)
- `celery`: worker para tareas
- `db`: PostgreSQL 15
- `redis`: cola para Celery

### Comandos útiles dentro del contenedor
```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py shell
```
El worker de Celery se reiniciará solo con cada cambio, usa Redis como broker (`redis://redis:6379/0`).

## Ejecución local sin Docker
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DJANGO_DEBUG=True  # y el resto de variables necesarias
python manage.py migrate
python manage.py runserver
```
Para lanzar el worker local:
```bash
celery -A badgeup worker -l info
```

## Flujo de validación de stickers
1. El usuario hace POST a `/api/stickers/<id>/unlock/` con `photo` (archivo) o `photo_url`.
2. Se genera/actualiza un `UserSticker` y se envía una tarea Celery `validate_user_sticker`.
3. La tarea llama a `achievements.services.analyze_user_sticker`:
   - Si no hay `OPENAI_API_KEY`, aprueba automáticamente y añade notas de simulación.
   - Si hay API key, usa `OpenAI Responses` con un prompt simple (vision multimodal).
4. Si la foto se aprueba, el usuario recibe puntos (`Sticker.reward_points`).

## Endpoints relevantes
| Método | Endpoint | Descripción |
| --- | --- | --- |
| `POST` | `/api/auth/register/` | Registro de usuario |
| `POST` | `/api/auth/login/` | Login + JWT (payload incluye datos del usuario) |
| `POST` | `/api/auth/token/refresh/` | Refrescar JWT |
| `GET/PATCH` | `/api/auth/profile/` | Perfil del usuario logueado |
| `GET` | `/api/auth/leaderboard/` | Top usuarios (por puntos) |
| `GET` | `/api/albums/` | Listado de álbumes |
| `GET` | `/api/albums/<id>/` | Detalle con stickers |
| `GET` | `/api/albums/stickers/<id>/` | Detalle de un sticker |
| `POST` | `/api/stickers/<id>/unlock/` | Subir foto y lanzar validación |

Todas las rutas (salvo registro/login/leaderboard) requieren autenticación con `Authorization: Bearer <token>`.

## Migrations & administración
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```
Panel admin disponible en `/admin/`.

## Testing y próximos pasos
- Añadir suite de tests (pytest o unittest + factory_boy) para validar flujos clave.
- Completar lógica real de validación (geolocalización, prompts detallados, reintentos).
- Configurar CI/CD (GitLab CI) con ejecución de tests y despliegue.
- Añadir documentación OpenAPI (e.g., drf-spectacular).

¡Listo! El backend queda preparado para conectar con tu frontend React y seguir iterando la experiencia de BadgeUp.

## Validación de stickers con OpenAI Vision

El backend puede usar OpenAI (visión) para validar si la foto del usuario coincide con el sticker:

- Configuración:
  - Añade `OPENAI_API_KEY` en `.env` (ya soportado en `settings.py`).
  - `USE_OPENAI_STICKER_VALIDATION` se activa automáticamente si hay API key.
- Dependencia: `openai>=1.0.0` (incluida en `requirements.txt`).
- Flujo:
  1. El usuario sube foto (UserSticker).
  2. La tarea Celery `validate_user_sticker` llama a `achievements.services.analyze_user_sticker`.
  3. Se envían a OpenAI la imagen de referencia del sticker, la foto del usuario y un prompt con nombre/álbum/descr.
  4. OpenAI responde JSON: `{"match_score": 0-1, "is_match": bool, "reason": "..."}`.
  5. Si `is_match=true` y `match_score>=0.6`, se aprueba; de lo contrario se rechaza. El score y notas se guardan en `validation_score` y `validation_notes`.
  6. Si no hay API key, se autoaprueba (modo dev) para no romper el flujo.
- Prueba manual:
  - Crea un sticker “Dodge Charger SRT Hellcat 2015–2023” con imagen de referencia.
  - Envía una foto real de un Hellcat como evidencia (POST `/api/stickers/<id>/unlock/` con `photo`).
  - La tarea debería dejar el UserSticker en `approved` con un `validation_score` alto.
- Ejemplo de payload enviado a OpenAI (resumen):
  - Modelo: `gpt-4.1-mini`
  - Input: prompt con texto del sticker + imágenes [`sticker.image_reference`, `user_sticker.photo`]
  - Respuesta esperada (JSON): `{"match_score":0.78,"is_match":true,"reason":"Coincide con Charger Hellcat 2015-2023"}`
