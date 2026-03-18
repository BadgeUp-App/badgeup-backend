import base64
import json
import logging
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
            model="gpt-4.1-mini",
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
            model="gpt-4.1-mini",
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
