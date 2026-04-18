import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Column, Integer
from sqlmodel import DateTime, Field, Identity, SQLModel, text


class Profile(SQLModel, table=True):
    id: uuid.UUID | None = Field(default_factory=uuid.uuid7, primary_key=True)
    display_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, Identity(), unique=True, index=True),
    )
    name: str = Field(index=True, unique=True, nullable=False)
    gender: str
    gender_probability: Decimal = Field(default=0, decimal_places=2)
    sample_size: int
    age: int
    age_group: str
    country_id: str
    country_probability: Decimal = Field(default=0, decimal_places=2)
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=text("now()")
        ),
    )
