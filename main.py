from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request

from database.database import create_db_and_tables
from routers.profiles import router as profiles_router
from utils.helpers import CORSJSONResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


app.include_router(profiles_router)
