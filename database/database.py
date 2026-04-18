from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, SQLModel, create_engine

from core.config import POSTGRES_URL

assert POSTGRES_URL is not None, "POSTGRES_URL environment variable is not set"

engine = create_engine(POSTGRES_URL)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
