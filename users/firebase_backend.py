import json
import logging
import os
import threading
from typing import Optional, Tuple

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

logger = logging.getLogger(__name__)

_init_lock = threading.Lock()
_initialized = False
_init_error: Optional[str] = None


def _load_credentials():
    path = os.getenv("FIREBASE_CREDENTIALS_PATH")
    if path and os.path.isfile(path):
        return credentials.Certificate(path)

    raw = os.getenv("FIREBASE_CREDENTIALS_JSON")
    if raw:
        data = json.loads(raw)
        return credentials.Certificate(data)

    return None


def ensure_initialized() -> Tuple[bool, Optional[str]]:
    global _initialized, _init_error
    if _initialized:
        return True, None

    with _init_lock:
        if _initialized:
            return True, None

        try:
            cred = _load_credentials()
            if cred is None:
                msg = (
                    "Firebase no configurado: faltan FIREBASE_CREDENTIALS_PATH "
                    "o FIREBASE_CREDENTIALS_JSON en el entorno."
                )
                logger.warning(msg)
                _init_error = msg
                return False, msg

            try:
                firebase_admin.initialize_app(cred)
            except ValueError:
                pass

            _initialized = True
            _init_error = None
            return True, None
        except Exception as exc:
            msg = f"No se pudo inicializar Firebase Admin: {exc}"
            logger.exception(msg)
            _init_error = msg
            return False, msg


def verify_id_token(token: str) -> Tuple[Optional[dict], Optional[str]]:
    ok, err = ensure_initialized()
    if not ok:
        return None, err
    try:
        return firebase_auth.verify_id_token(token), None
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        logger.info("ID token invalido: %s", msg)
        return None, msg
