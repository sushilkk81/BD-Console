from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings

settings = get_settings()

app = FastAPI(title="BD Console API")

from app.routers.auth import router as auth_router
app.include_router(auth_router)

from app.routers.requests import router as requests_router
app.include_router(requests_router)

from app.routers.kams import router as kams_router
app.include_router(kams_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
