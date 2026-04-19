import asyncio
from decimal import Decimal

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from database.database import SessionDep
from models.profile import CreateProfile, Profile
from utils.helpers import CORSJSONResponse, _serialize, classify_age

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.post("")
async def create_profile(payload: CreateProfile, session: SessionDep):
    async with httpx.AsyncClient() as client:
        try:
            name = payload.name

            if not name:
                return CORSJSONResponse(
                    {"status": "error", "message": "missing or empty name"},
                    status_code=400,
                )

            existing = session.exec(select(Profile).where(Profile.name == name)).first()

            if existing:
                return CORSJSONResponse(_serialize(existing, exists=True), 200)

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

            genderize_data: dict = genderize_response.json()
            nationalize_data: dict = nationalize_response.json()
            agify_data: dict = agify_response.json()

            if genderize_data.get("gender") is None or genderize_data.get("count") == 0:
                return CORSJSONResponse(
                    content={
                        "status": "error",
                        "message": "Genderize returned an invalid response",
                    },
                    status_code=502,
                )
            if agify_data.get("age") is None:
                return CORSJSONResponse(
                    content={
                        "status": "error",
                        "message": "Agify returned an invalid response",
                    },
                    status_code=502,
                )

            if nationalize_data.get("count") == 0:
                return CORSJSONResponse(
                    content={
                        "status": "error",
                        "message": "Nationalize returned an invalid response",
                    },
                    status_code=502,
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

            # add person to table
            session.add(person)
            try:
                session.commit()
            # names must be unique in the database
            except IntegrityError:
                # undo commit and return existing profile
                session.rollback()
                existing = session.exec(
                    select(Profile).where(Profile.name == name)
                ).one()
                return CORSJSONResponse(_serialize(existing, exists=True), 200)

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


@router.get("/{id}")
async def get_profile(id: int, session: SessionDep):
    try:
        if not id:
            return CORSJSONResponse(
                {"status": "error", "message": "empty or missing id parameter"}
            )

        profile = session.exec(select(Profile).where(Profile.display_id == id)).first()

        if profile:
            return CORSJSONResponse(_serialize(profile))
        else:
            return CORSJSONResponse(
                content={"status": "error", "message": "profile not found"},
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


@router.get("")
async def get_profiles(
    session: SessionDep,
    gender: str | None = None,
    country_id: str | None = None,
    age_group: str | None = None,
):
    try:
        statement = select(Profile)

        if gender:
            statement = statement.where(Profile.gender == gender.lower())
        if country_id:
            statement = statement.where(Profile.country_id == country_id.upper())
        if age_group:
            statement = statement.where(Profile.age_group == age_group.lower())

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
            return CORSJSONResponse(
                content={"status": "error", "message": "profile not found"},
                status_code=404,
            )
    except Exception:
        raise HTTPException(
            detail={"status": "error", "message": "An unexpected error occurred"},
            status_code=500,
        )


@router.delete("/{id}")
async def delete_profile(session: SessionDep, id: int):
    try:
        profile = session.exec(select(Profile).where(Profile.display_id == id)).first()

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
