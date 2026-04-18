from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, SQLModel, create_engine

from core.config import POSTGRES_URL

assert POSTGRES_URL is not None, "POSTGRES_URL environment variable is not set"

# Ensure SQLAlchemy uses the psycopg v3 driver instead of psycopg2.
# Rewrite both "postgresql://" and "postgres://" schemes accordingly.
_db_url = POSTGRES_URL
for _prefix in ("postgresql://", "postgres://"):
    if _db_url.startswith(_prefix):
        _db_url = "postgresql+psycopg://" + _db_url[len(_prefix):]
        break

engine = create_engine(_db_url)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
