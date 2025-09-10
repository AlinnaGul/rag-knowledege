# scripts/seed_admin.py
from api.db import engine, SessionLocal
from api import models
from api.security import get_password_hash

models.Base.metadata.create_all(bind=engine)

db = SessionLocal()
email = "admin@admin.com"
pwd   = "Admin#123456"

user = db.query(models.User).filter_by(email=email).first()
if not user:
    user = models.User(
        email=email,
        name="Admin",
        password_hash=get_password_hash(pwd),
        role="admin",
        active=True,
    )
    db.add(user)
    db.commit()
    print(f"Seeded admin: {email} / {pwd}")
else:
    print(f"Admin already exists: {email}")
