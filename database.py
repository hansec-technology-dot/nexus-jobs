from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# SQLite URL — swap this for PostgreSQL on Render by reading from an env var:
# import os; DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./remote_work_insider.db")
DATABASE_URL = "sqlite:///./remote_work_insider.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Required for SQLite + FastAPI threading
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """
    Dependency-injected DB session for FastAPI routes.
    Yields a session and ensures it is closed after the request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Creates all tables defined via Base.metadata.
    Called once at app startup. Safe to call multiple times (CREATE IF NOT EXISTS).
    Import models here to ensure they are registered on Base before create_all.
    """
    import models  # noqa: F401 — registers all ORM models on Base
    Base.metadata.create_all(bind=engine)
