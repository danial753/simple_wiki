from app import app, db
from sqlalchemy import text

# ایجاد یک application context
with app.app_context():
    with db.engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE page ADD COLUMN gallery TEXT"))
        except Exception as e:
            print(f"Error adding 'gallery': {e}")

        try:
            conn.execute(text("ALTER TABLE page ADD COLUMN videos TEXT"))
        except Exception as e:
            print(f"Error adding 'videos': {e}")

        try:
            conn.execute(text("ALTER TABLE page ADD COLUMN personnel TEXT"))
        except Exception as e:
            print(f"Error adding 'personnel': {e}")

    print("DB Updated ✅")
