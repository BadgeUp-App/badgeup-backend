import base64
import logging
import os
from typing import Optional

from django.conf import settings

from badgeup.openai_client import get_openai_client

logger = logging.getLogger(__name__)

PREFILTER_SYSTEM = (
    "Eres un filtro previo de imagenes para una app de stickers coleccionables. "
    "Tu unica tarea: decidir si la foto contiene ALGO RECONOCIBLE que valga la pena "
    "analizar (objetos, animales, plantas, vehiculos, comida, lugares, personas, arte) "
    "o si es BASURA (foto borrosa, foto del techo, dedo cubriendo lente, pared blanca, "
    "ruido random).\n\n"
    "Responde SOLO con uno de estos dos JSONs:\n"
    '{"collectible": true}\n'
    '{"collectible": false, "reason": "<motivo en 1 frase corta>"}'
)


def is_enabled() -> bool:
    return bool(getattr(settings, "VISION_PREFILTER_ENABLED", True))


def is_collectible(image_bytes: bytes) -> Optional[dict]:
    if not is_enabled() or not image_bytes:
        return None
    try:
        client = get_openai_client()
    except Exception:
        logger.exception("vision_prefilter cannot init openai client")
        return None
    try:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        completion = client.chat.completions.create(
            model=os.getenv("VISION_PREFILTER_MODEL", "gpt-4o-mini"),
            response_format={"type": "json_object"},
            max_tokens=50,
            messages=[
                {"role": "system", "content": PREFILTER_SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64}",
                                "detail": "low",
                            },
                        },
                        {
                            "type": "text",
                            "text": "Es esto algo reconocible para coleccionar?",
                        },
                    ],
                },
            ],
        )
        import json

        raw = completion.choices[0].message.content or "{}"
        return json.loads(raw)
    except Exception:
        logger.exception("vision_prefilter call failed")
        return None
