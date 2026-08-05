import os
from tinydb import TinyDB

DB_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DB_DIR, "suppliers.json")


def get_db() -> TinyDB:
    os.makedirs(DB_DIR, exist_ok=True)
    return TinyDB(DB_PATH, ensure_ascii=False)
