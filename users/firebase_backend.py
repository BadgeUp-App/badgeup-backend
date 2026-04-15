import json
import logging
import os
import threading
from typing import Optional

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

logger = logging.getLogger(__name__)

_init_lock = threading.Lock()
_initialized = False


def _load_credentials():
    path = os.getenv("FIREBASE_CREDENTIALS_PATH")
    if path and os.path.isfile(path):
        return credentials.Certificate(path)

    raw = os.getenv("FIREBASE_CREDENTIALS_JSON")
    if raw:
        data = json.loads(raw)
        return credentials.Certificate(data)

    return None


def ensure_initialized():
    global _initialized
    if _initialized:
        return True

    with _init_lock:
        if _initialized:
            return True

        try:
            cred = _load_credentials()
            if cred is None:
                logger.warning(
                    "Firebase no configurado: falta FIREBASE_CREDENTIALS_PATH o FIREBASE_CREDENTIALS_JSON"
                )
                return False

            try:
                firebase_admin.initialize_app(cred)
            except ValueError:
                pass

            _initialized = True
            return True
        except Exception as exc:
            logger.exception("No se pudo inicializar Firebase Admin: %s", exc)
            return False


def verify_id_token(token: str) -> Optional[dict]:
    if not ensure_initialized():
        return None
    try:
        return firebase_auth.verify_id_token(token)
    except Exception as exc:
        logger.info("ID token invalido: %s", exc)
        return None
