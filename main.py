import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal, getcontext
from typing import Annotated

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from sqlalchemy import Column, Identity, Integer, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import DateTime, Field, Session, SQLModel, create_engine, select

load_dotenv()

POSTGRES_URL = os.getenv("POSTGRES_URL")

engine = create_engine(POSTGRES_URL)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


PRECISION = 2
getcontext().prec = PRECISION


class CORSJSONResponse(JSONResponse):
    def __init__(
        self,
        content,
        status_code: int = 200,
        headers={"Access-Control-Allow-Origin": "*"},
    ) -> None:
        super().__init__(content, status_code, headers)


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


def classify_age(age: int):
    if 0 <= age <= 12:
        age_group = "child"
    elif 13 <= age <= 19:
        age_group = "teenager"
    elif 20 <= age <= 59:
        age_group = "adult"
    else:
        age_group = "senior"

    return age_group


def _serialize(person: Profile, message: str = "success", all: bool = False) -> dict:
    if all:
        return {
            "status": message,
            "data": {
                "id": f"id-{person.display_id}",
                "name": person.name,
                "gender": person.gender,
                "age": person.age,
                "age_group": person.age_group,
                "country_id": person.country_id,
            },
        }

    return {
        "status": message,
        "data": {
            "id": str(person.id),
            "name": person.name,
            "gender": person.gender,
            "gender_probability": round(float(person.gender_probability), 2),
            "sample_size": person.sample_size,
            "age": person.age,
            "age_group": person.age_group,
            "country_id": person.country_id,
            "country_probability": round(float(person.country_probability), 2),
            "created_at": person.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    }


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# for httpx.HTTPStatusError requests
@app.exception_handler(httpx.HTTPStatusError)
async def external_api_exception_handler(request: Request, exc: httpx.HTTPStatusError):
    api_name = exc.request.headers.get("api_name")
    return CORSJSONResponse(
        {"status": "error", "message": f"{api_name} returned an invalid response"},
        status_code=502,
    )


@app.exception_handler(HTTPException)
async def global_exception_handler(request: Request, exc: HTTPException):
    return CORSJSONResponse(content=exc.detail, status_code=exc.status_code)


@app.post("/api/profiles")
async def classify(name: str, session: SessionDep):
    async with httpx.AsyncClient() as client:
        try:
            existing = session.exec(select(Profile).where(Profile.name == name)).first()

            if existing:
                return CORSJSONResponse(
                    _serialize(existing, message="Profile Already Exists"), 200
                )

            genderize_url = "https://api.genderize.io"
            nationalize_url = "https://api.nationalize.io"
            agify_url = "https://api.agify.io"

            params = {"name": name}
            tasks = [
                client.get(
                    genderize_url,
                    params=params,
                    headers={"api_name": "Genderize"},
                    timeout=5,
                ),
                client.get(
                    nationalize_url,
                    params=params,
                    headers={"api_name": "Nationalize"},
                    timeout=5,
                ),
                client.get(
                    agify_url,
                    params=params,
                    headers={"api_name": "Agify"},
                    timeout=5,
                ),
            ]

            (
                genderize_response,
                nationalize_response,
                agify_response,
            ) = await asyncio.gather(*tasks)

            genderize_response.raise_for_status()
            nationalize_response.raise_for_status()
            agify_response.raise_for_status()

            ### process
            genderize_data: dict = genderize_response.json()
            nationalize_data: dict = nationalize_response.json()
            agify_data: dict = agify_response.json()

            if genderize_data.get("gender") is None or genderize_data.get("count") == 0:
                raise HTTPException(
                    status_code=502,
                    detail={
                        "status": "error",
                        "message": "Genderize returned an invalid response",
                    },
                )
            if agify_data.get("age") is None:
                raise HTTPException(
                    502,
                    {
                        "status": "error",
                        "message": "Agify returned an invalid response",
                    },
                )
            if nationalize_data.get("count") == 0:
                raise HTTPException(
                    502,
                    {
                        "status": "error",
                        "message": "Nationalize returned an invalid response",
                    },
                )

            country = nationalize_data["country"][0]

            person = Profile(
                name=name,
                gender=genderize_data["gender"],
                gender_probability=genderize_data["probability"],
                sample_size=genderize_data["count"],
                age=agify_data["age"],
                age_group=classify_age(agify_data["age"]),
                country_id=country.get("country_id"),
                country_probability=Decimal(country["probability"]),
            )

            session.add(person)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.exec(
                    select(Profile).where(Profile.name == name)
                ).one()
                return CORSJSONResponse(
                    _serialize(existing, message="Profile Already Exists"), 200
                )

            session.refresh(person)
            return CORSJSONResponse(
                _serialize(person),
                201,
            )
        except Exception:
            raise HTTPException(
                detail={"status": "error", "message": "An unexpected error occurred"},
                status_code=500,
            )


@app.get("/api/profiles/{id}")
async def get_profile(display_id: int, session: SessionDep):
    try:
        profile = session.exec(
            select(Profile).where(Profile.display_id == display_id)
        ).first()

        if profile:
            return CORSJSONResponse(_serialize(profile))
        else:
            raise HTTPException(
                detail={"status": "error", "message": "profile not found"},
                status_code=404,
            )
    except RequestValidationError:
        return HTTPException(
            detail={"status": "error", "message": "invalid type int"}, status_code=422
        )
    except Exception:
        raise HTTPException(
            detail={"status": "error", "message": "An unexpected error occurred"},
            status_code=500,
        )


@app.get("/api/profiles")
async def get_profiles(
    session: SessionDep,
    gender: str | None = None,
    country_id: str | None = None,
    age_group: str | None = None,
):
    try:
        statement = select(Profile)

        # builds select statement dynamically, lower() and .upper() for case insensitivity
        if gender:
            statement = statement.where(Profile.gender == gender.lower())
        if country_id:
            statement = statement.where(Profile.country_id == country_id.upper())
        if age_group:
            statement = statement.where(Profile.age_group == age_group.lower())

        # if no filters provided, return an error instead of all profiles
        if not gender and not country_id and not age_group:
            raise HTTPException(
                detail={
                    "status": "error",
                    "message": "missing or empty parameters",
                },
                status_code=400,
            )

        # execute the select statement and returns a sequence of profiles
        profiles = session.exec(statement).fetchall()
        count = len(profiles)

        if count:
            results = []
            for profile in profiles:
                results.append(_serialize(profile, all=True))

            return CORSJSONResponse(
                {"status": "success", "count": count, "data": results},
            )
        else:
            raise HTTPException(
                detail={"status": "error", "message": "profile not found"},
                status_code=404,
            )
    except Exception:
        raise HTTPException(
            detail={"status": "error", "message": "An unexpected error occurred"},
            status_code=500,
        )


@app.delete("/api/profiles/{id}")
async def delete_profile(session: SessionDep, display_id: int):
    try:
        profile = session.exec(
            select(Profile).where(Profile.display_id == display_id)
        ).first()

        if profile:
            session.delete(profile)
            session.commit()
            return CORSJSONResponse(content=None, status_code=204)
        else:
            return CORSJSONResponse(
                {"status": "error", "message": "profile not found"},
                404,
            )
    except Exception:
        raise HTTPException(
            detail={"status": "error", "message": "An unexpected error occurred"},
            status_code=500,
        )


if __name__ == "__main__":
    pass
