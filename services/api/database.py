import logging
import os

from tinydb import TinyDB

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DB_DIR, "suppliers.json")


def get_db() -> TinyDB:
    try:
        os.makedirs(DB_DIR, exist_ok=True)
        return TinyDB(DB_PATH, ensure_ascii=False)
    except OSError as exc:
        logger.exception("No se pudo inicializar la base de datos en %s", DB_PATH)
        raise RuntimeError("No se pudo inicializar la base de datos.") from exc
