from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = "cafe-pos-secret-key"
    DATABASE = str(BASE_DIR / "temps" / "cafe_pos.sqlite3")
    SCHEMA_FILE = str(BASE_DIR / "temps" / "database.db")
    SHOP_NAME = "Mont Cafe"
    SHOP_BIR_REGISTRATION = "BIR Reg. No. 000-123-456-789"
