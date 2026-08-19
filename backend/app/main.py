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

from app.routers.customer_visits import router as customer_visits_router
app.include_router(customer_visits_router)

from app.routers.reference_products import router as reference_products_router
app.include_router(reference_products_router)

from app.routers.dashboard import router as dashboard_router
app.include_router(dashboard_router)

from app.routers.notifications import router as notifications_router
app.include_router(notifications_router)

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
