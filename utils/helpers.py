from fastapi.responses import JSONResponse

from models.profile import Profile


class CORSJSONResponse(JSONResponse):
    def __init__(
        self,
        content,
        status_code: int = 200,
        headers={"Access-Control-Allow-Origin": "*"},
    ) -> None:
        super().__init__(content, status_code, headers)


def classify_age(age: int) -> str:
    if 0 <= age <= 12:
        return "child"
    elif 13 <= age <= 19:
        return "teenager"
    elif 20 <= age <= 59:
        return "adult"
    else:
        return "senior"


def _serialize(person: Profile, exists: bool = False, all: bool = False) -> dict:
    if all:
        return {
            "id": f"id-{person.display_id}",
            "name": person.name,
            "gender": person.gender,
            "age": person.age,
            "age_group": person.age_group,
            "country_id": person.country_id,
        }

    if exists:
        return {
            "status": "success",
            "message": "already exists",
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

    return {
        "status": "success",
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
