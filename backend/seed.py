from shared.database import Base, SessionLocal, engine
from users.models import User
from users.service import get_password_hash

TEST_EMAIL = "test@cedia.com"
TEST_PASSWORD = "Test1234!"


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == TEST_EMAIL).first()
        if existing is None:
            db.add(
                User(
                    email=TEST_EMAIL,
                    password_hash=get_password_hash(TEST_PASSWORD),
                    name="Usuario Test",
                )
            )
            db.commit()
            print("Seed creado")
        else:
            print("Seed ya existe")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
