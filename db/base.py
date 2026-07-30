import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


DB_URL = os.getenv("DB_URL", "sqlite:///bikereview.db")

engine = create_engine(DB_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_session():
    return SessionLocal()


def init_db():
    import db.models  # noqa: F401 — registers models with Base
    Base.metadata.create_all(engine)
