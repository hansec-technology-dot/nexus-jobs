from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# SQLite URL — swap for PostgreSQL on Render by changing this env var
SQLALCHEMY_DATABASE_URL = "sqlite:///./remote_work_insider.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},  # Required for SQLite
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """
    FastAPI dependency that yields a SQLAlchemy session and ensures cleanup.
    Usage: db: Session = Depends(get_db)
    For production with PostgreSQL, remove check_same_thread and adjust URL.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Creates all tables defined in models.py.
    Called at application startup in main.py.
    Import models before calling so Base has all metadata registered.
    """
    import models  # noqa: F401 — ensures models register with Base
    Base.metadata.create_all(bind=engine)
