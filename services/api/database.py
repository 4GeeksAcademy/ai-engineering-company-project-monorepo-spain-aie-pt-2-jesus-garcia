import logging
import os

from dotenv import load_dotenv
from sqlmodel import Session, create_engine
from tinydb import TinyDB

load_dotenv()

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DB_DIR, "suppliers.json")

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL) if DATABASE_URL else None


def get_tinydb() -> TinyDB:
    try:
        os.makedirs(DB_DIR, exist_ok=True)
        return TinyDB(DB_PATH, ensure_ascii=False)
    except OSError as exc:
        logger.exception("No se pudo inicializar la base de datos en %s", DB_PATH)
        raise RuntimeError("No se pudo inicializar la base de datos.") from exc


def get_db():
    if engine is None:
        raise RuntimeError(
            "DATABASE_URL no está configurada. Definela en el entorno o en .env para usar la base de datos SQL."
        )
    with Session(engine) as session:
        yield session