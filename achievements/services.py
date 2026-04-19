import base64
import json
import logging
import os
from typing import Any, Dict, Iterable, Optional

from django.conf import settings

from albums.models import Sticker
from badgeup.openai_client import get_openai_client
from .models import UserSticker

logger = logging.getLogger(__name__)


def _image_payload(user_sticker: UserSticker) -> Optional[Dict[str, Any]]:
    if user_sticker.photo_url:
        return {"type": "input_image", "image_url": user_sticker.photo_url}

    if user_sticker.photo:
        try:
            with user_sticker.photo.open("rb") as uploaded:
                encoded = base64.b64encode(uploaded.read()).decode("utf-8")
            return {
                "type": "input_image",
                "image_url": f"data:image/jpeg;base64,{encoded}",
            }
        except FileNotFoundError:
            logger.warning("UserSticker photo file not found for id=%s", user_sticker.id)
        except (NotImplementedError, ValueError):
            try:
                return {"type": "input_image", "image_url": user_sticker.photo.url}
            except ValueError:
                logger.warning("Unable to resolve URL for UserSticker photo id=%s", user_sticker.id)

    return None


def _sticker_reference_payload(sticker: Sticker) -> Optional[Dict[str, Any]]:
    """
    Build an image payload for the sticker reference if available.
    """
    if not sticker.image_reference:
        return None
    try:
        with sticker.image_reference.open("rb") as ref:
            encoded = base64.b64encode(ref.read()).decode("utf-8")
        return {"type": "input_image", "image_url": f"data:image/jpeg;base64,{encoded}"}
    except FileNotFoundError:
        logger.warning("Sticker reference image not found for id=%s", sticker.id)
    except (NotImplementedError, ValueError):
        try:
            return {"type": "input_image", "image_url": sticker.image_reference.url}
        except ValueError:
            logger.warning("Unable to resolve URL for sticker reference id=%s", sticker.id)
    return None


def analyze_car_photo(photo_file, stickers: Iterable[Sticker]) -> dict[str, Any] | None:
    """
    Analiza la foto con OpenAI y regresa un JSON con recognized/make/model/.../fun_fact.
    """
    if not settings.USE_OPENAI_STICKER_VALIDATION:
        return {"error": "validación por IA deshabilitada"}

    try:
        client = get_openai_client()
    except Exception:  # pragma: no cover
        logger.exception("No se pudo inicializar el cliente de OpenAI")
        return None

    try:
        raw = photo_file.read()
        b64 = base64.b64encode(raw).decode("utf-8")
    except Exception:
        logger.exception("No se pudo leer la foto del usuario")
        return None
    finally:
        try:
            photo_file.seek(0)
        except Exception:
            pass

    stickers_text = "\n".join(
        f"- ID {s.id}: {s.name} — {s.description or ''}" for s in stickers
    ) or "No hay stickers en este álbum."

    system_msg = (
        "Eres un experto en autos. Recibes UNA foto y una lista de stickers de un álbum (solo texto). "
        "Debes identificar el coche usando SOLO la foto y tu conocimiento, y luego decidir si alguno de los stickers coincide.\n\n"
        "Responde SIEMPRE un JSON válido con este esquema EXACTO:\n"
        "{\n"
        '  \"recognized\": boolean,            # true si es claramente un coche identificable\n'
        '  \"make\": string|null,\n'
        '  \"model\": string|null,\n'
        '  \"generation\": string|null,\n'
        '  \"year_range\": string|null,\n'
        '  \"confidence\": number,            # 0-1 sobre el match con UN sticker del álbum\n'
        '  \"sticker_id\": number|null,       # ID de la lista de stickers, o null si no hay sticker para este coche\n'
        '  \"reason\": string,                # explica por qué elegiste ese sticker o por qué no hay match\n'
        '  \"fun_fact\": string               # un dato curioso corto sobre ese modelo; si no es un coche, un mensaje tipo \"no es un coche\"\n'
        "}\n"
        "Si NO es un coche (o no estás seguro), usa recognized=false, deja make/model/generation/year_range en null, "
        "sticker_id=null, confidence=0, y en fun_fact pon un mensaje divertido tipo \"Uy, esto no parece un coche.\""
    )

    user_text = (
        "Lista de stickers disponibles en el álbum:\n"
        f"{stickers_text}\n\n"
        "Analiza la foto y devuelve SOLO el JSON, sin texto extra."
    )

    try:
        completion = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1"),
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_msg},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                },
            ],
            max_tokens=400,
        )
        raw_content = completion.choices[0].message.content or "{}"
        data = json.loads(raw_content)
    except Exception:
        logger.exception("No se pudo parsear JSON de OpenAI")
        return None

    data.setdefault("recognized", False)
    data.setdefault("make", None)
    data.setdefault("model", None)
    data.setdefault("generation", None)
    data.setdefault("year_range", None)
    data.setdefault("confidence", 0.0)
    data.setdefault("sticker_id", None)
    data.setdefault("reason", "")
    data.setdefault("fun_fact", "")
    return data


def analyze_photo_global(photo_file, albums_qs) -> dict[str, Any] | None:
    if not settings.USE_OPENAI_STICKER_VALIDATION:
        return {"error": "validacion por IA deshabilitada"}

    try:
        client = get_openai_client()
    except Exception:
        logger.exception("No se pudo inicializar el cliente de OpenAI")
        return None

    try:
        raw = photo_file.read()
        b64 = base64.b64encode(raw).decode("utf-8")
    except Exception:
        logger.exception("No se pudo leer la foto del usuario")
        return None
    finally:
        try:
            photo_file.seek(0)
        except Exception:
            pass

    person_tags = {"personas", "profes", "estudiantes", "maestros"}
    catalog_lines = []
    reference_imgs = []

    try:
        for album in albums_qs:
            tags = album.tags or album.theme or ""
            tag_set = {t.strip().lower() for t in tags.split(",") if t.strip()}
            is_person_album = bool(tag_set & person_tags)

            sticker_parts = []
            for s in album.stickers.all():
                sticker_parts.append(f"  - ID {s.id}: {s.name} -- {s.description or ''}")
                if is_person_album:
                    multi_refs = list(s.reference_photos.all())
                    if multi_refs:
                        for rp in multi_refs:
                            try:
                                url = rp.photo.url
                                if url and url.startswith("http"):
                                    lbl = rp.label or ""
                                    reference_imgs.append((s.id, s.name, url, lbl))
                            except Exception:
                                pass
                    else:
                        ref_field = getattr(s, "reference_photo", None) or s.image_reference
                        if ref_field:
                            try:
                                url = ref_field.url
                                if url and url.startswith("http"):
                                    reference_imgs.append((s.id, s.name, url, ""))
                            except Exception:
                                pass

            sticker_list = "\n".join(sticker_parts)
            catalog_lines.append(
                f"Album ID {album.id}: \"{album.title}\" [tags: {tags}]\nStickers:\n{sticker_list}"
            )
    except Exception:
        logger.exception("Error building sticker catalog")
        reference_imgs = []

    catalog_text = "\n\n".join(catalog_lines) or "No hay albums disponibles."

    custom_prompts = []
    for album in albums_qs:
        if hasattr(album, 'custom_prompt') and album.custom_prompt:
            custom_prompts.append(f"Album \"{album.title}\": {album.custom_prompt}")

    has_refs = len(reference_imgs) > 0

    system_msg = (
        "Eres un sistema de reconocimiento visual para una app de stickers coleccionables. "
        "Recibes UNA foto y un catalogo de albums con tags y stickers.\n\n"
        "PASO 1 — CLASIFICAR LA FOTO:\n"
        "Determina que hay en la foto. Usa los TAGS de cada album para saber que categoria manejan:\n"
        "- Tags con 'personas','profes','estudiantes' = albums de PERSONAS.\n"
        "- Tags con 'autos','carros','pickup','deportivos','jdm' = albums de VEHICULOS.\n"
        "- Otros tags = usa tu criterio para el tipo de contenido.\n\n"
        "PASO 2 — BUSCAR MATCH EN ALBUMS RELEVANTES:\n"
        "Solo busca en albums cuyas tags sean compatibles con lo que ves en la foto.\n\n"
        "REGLAS POR CATEGORIA:\n\n"
        "VEHICULOS:\n"
        "- Identifica MARCA, MODELO EXACTO, GENERACION y RANGO DE ANIO.\n"
        "- Un Toyota Tacoma NO es una Tundra. Un Mustang GT NO es un Shelby GT350.\n"
        "- Fijate en parrilla, faros, proporciones, badges, rines, lineas de carroceria.\n"
        "- Confidence 0.9+ solo si estas SEGURO del modelo exacto.\n"
        "- Si hay MAS DE UN vehiculo, devuelve un match por cada uno.\n\n"
        "REGLA CRITICA — PRECISION SOBRE TODO:\n"
        "- SIEMPRE elige el sticker que MEJOR coincida con lo que ves, sin importar nada mas.\n"
        "- NUNCA evites un match exacto para elegir uno 'parecido'. Si ves una Toyota Tacoma "
        "y existe el sticker 'Toyota Tacoma', ese es el match correcto. No elijas 'Toyota Hilux' "
        "ni ningun otro modelo similar solo porque crees que seria mejor.\n"
        "- Tu UNICO criterio es la precision visual. No intentes ser creativo ni diversificar.\n\n"
    )

    if has_refs:
        system_msg += (
            "PERSONAS CON REFERENCIA VISUAL:\n"
            "Se incluyen IMAGENES DE REFERENCIA de los stickers de personas. "
            "Compara VISUALMENTE la persona de la foto del usuario contra cada referencia. "
            "Fijate en forma de la cara, rasgos faciales, complexion, barba, lentes, "
            "peinado, vestimenta y contexto general.\n"
            "- Confidence 0.85+ si el parecido es claro.\n"
            "- Si hay MAS DE UNA persona reconocible, devuelve un match por cada una.\n\n"
        )
    else:
        system_msg += (
            "PERSONAS:\n"
            "- Lee el nombre y descripcion de cada sticker del album de personas.\n"
            "- Compara la persona de la foto con las descripciones disponibles.\n"
            "- Confidence 0.8+ si la persona coincide claramente con un sticker.\n"
            "- Si hay MAS DE UNA persona reconocible, devuelve un match por cada una.\n\n"
        )

    system_msg += (
        "REGLA DE MULTIPLES ITEMS:\n"
        "- Si la foto muestra VARIOS objetos, animales, plantas, personas o vehiculos, "
        "devuelve UN match por CADA uno que coincida con algun sticker.\n"
        "- Ejemplo: foto con un perro y un gato = 2 matches si ambos tienen sticker.\n"
        "- Ejemplo: foto con 3 flores distintas = 3 matches.\n"
        "- No te limites a un solo match por foto.\n\n"
        "GENERAL:\n"
        "- Si tienes duda, usa confidence menor a 0.7 y NO hagas match.\n"
        "- Si detectas algo que no esta en ningun album, dilo en reason.\n\n"
    )

    if custom_prompts:
        system_msg += (
            "INSTRUCCIONES ESPECIALES POR ALBUM:\n"
            + "\n".join(custom_prompts)
            + "\n\n"
        )

    system_msg += (
        "Responde SIEMPRE un JSON valido con este esquema EXACTO:\n"
        "{\n"
        '  "recognized": boolean,\n'
        '  "item_count": number,\n'
        '  "photo_category": string,\n'
        '  "matches": [\n'
        "    {\n"
        '      "detected_item": string,\n'
        '      "detected_category": string,\n'
        '      "confidence": number,\n'
        '      "album_id": number|null,\n'
        '      "sticker_id": number|null,\n'
        '      "reason": string\n'
        "    }\n"
        "  ],\n"
        '  "fun_fact": string\n'
        "}\n"
        "Si NO reconoces nada, usa recognized=false, item_count=0, matches=[], "
        "y un mensaje amigable en fun_fact."
    )

    content = [
        {"type": "text", "text": f"Catalogo de albums y stickers:\n{catalog_text}\n\n"},
    ]

    if reference_imgs:
        content.append(
            {"type": "text", "text": "IMAGENES DE REFERENCIA (stickers de personas):\n"}
        )
        for sid, sname, img_url, lbl in reference_imgs[:20]:
            tag = f" [{lbl}]" if lbl else ""
            content.append(
                {"type": "text", "text": f"Referencia sticker ID {sid} ({sname}){tag}:"}
            )
            content.append(
                {"type": "image_url", "image_url": {"url": img_url}}
            )

    content.append(
        {"type": "text", "text": "\nFoto del usuario a analizar:"}
    )
    content.append(
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
    )
    content.append(
        {"type": "text", "text": "Analiza la foto, clasifica lo que ves, busca en los albums relevantes y devuelve SOLO el JSON."}
    )

    try:
        completion = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1"),
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": content},
            ],
            max_tokens=800,
        )
        raw_content = completion.choices[0].message.content or "{}"
        data = json.loads(raw_content)
    except Exception:
        logger.exception("No se pudo parsear JSON de OpenAI (global scan)")
        return None

    data.setdefault("recognized", False)
    data.setdefault("item_count", data.get("vehicle_count", 0))
    data.setdefault("photo_category", "unknown")
    data.setdefault("matches", [])
    data.setdefault("fun_fact", "")

    if not data["matches"] and data.get("sticker_id"):
        data["matches"] = [{
            "detected_item": data.get("detected_item", ""),
            "detected_category": data.get("detected_category", ""),
            "confidence": float(data.get("confidence", 0)),
            "album_id": data.get("album_id"),
            "sticker_id": data.get("sticker_id"),
            "reason": data.get("reason", ""),
        }]
        data["item_count"] = 1

    for m in data["matches"]:
        m.setdefault("confidence", 0.0)
        m.setdefault("sticker_id", None)
        m.setdefault("album_id", None)
        m.setdefault("detected_item", "")
        m.setdefault("detected_category", "")
        m.setdefault("reason", "")

    return data


def analyze_user_sticker(user_sticker: UserSticker) -> dict[str, Any]:
    """
    Validate a user sticker submission using OpenAI Vision when enabled.
    Falls back to auto-approve when no API key is configured.
    """

    user_image = _image_payload(user_sticker)
    if not user_image:
        return {"approved": False, "reason": "No image provided"}

    sticker: Sticker = user_sticker.sticker
    reference_image = _sticker_reference_payload(sticker)

    if not settings.USE_OPENAI_STICKER_VALIDATION:
        return {
            "approved": True,
            "reason": "OpenAI validation disabled or missing API key - auto-approved (development mode).",
            "details": {},
        }

    try:
        client = get_openai_client()
    except Exception as exc:  # pragma: no cover - guarded by flag
        logger.exception("OpenAI client unavailable: %s", exc)
        return {"approved": False, "error": str(exc)}

    prompt_parts = [
        "Evalúa si la foto del usuario corresponde al mismo automóvil que el sticker de referencia.",
        f"Sticker: {sticker.name}.",
    ]
    if sticker.album:
        prompt_parts.append(f"Álbum: {sticker.album.title}.")
    if sticker.description:
        prompt_parts.append(f"Descripción: {sticker.description}.")

    prompt_parts.append(
        'Responde SOLO en JSON con la forma: {"match_score": 0-1, "is_match": true|false, "reason": "texto breve"}'
    )
    prompt = " ".join(prompt_parts)

    content = [
        {"type": "input_text", "text": prompt},
    ]
    if reference_image:
        content.append(reference_image)
    content.append(user_image)

    try:
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1"),
            input=[
                {
                    "role": "user",
                    "content": content,
                }
            ],
            max_output_tokens=200,
        )
        raw_output = response.output_text.strip()
        data = json.loads(raw_output)
        match_score = float(data.get("match_score", 0) or 0)
        is_match = bool(data.get("is_match"))
        reason = data.get("reason", "")
        approved = is_match and match_score >= 0.6
        request_id = getattr(response, "id", None)

        return {
            "approved": approved,
            "match_score": match_score,
            "is_match": is_match,
            "reason": reason,
            "raw_response": data,
            "request_id": request_id,
        }

    except json.JSONDecodeError as exc:
        logger.exception("Failed to parse OpenAI response for UserSticker %s", user_sticker.id)
        return {"approved": False, "error": f"Invalid JSON response: {exc}"}
    except Exception as exc:  # pragma: no cover - external dependency
        logger.exception("OpenAI validation failed for UserSticker %s", user_sticker.id)
        return {"approved": False, "error": str(exc)}
