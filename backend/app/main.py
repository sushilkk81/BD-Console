import math

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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

from app.routers.reference_lookup import router as reference_lookup_router
app.include_router(reference_lookup_router)

from app.routers.dashboard import router as dashboard_router
app.include_router(dashboard_router)

from app.routers.notifications import router as notifications_router
app.include_router(notifications_router)

from app.forecasting_engine.api.routes import router as forecasting_router
app.include_router(forecasting_router)

def _json_safe(value):
    """Replace non-finite floats with their names so a response can be encoded.

    Starlette's JSONResponse serialises with allow_nan=False. FastAPI's default
    validation handler echoes the offending input back in the 422 body, so a request
    carrying a bare NaN or Infinity literal made the error response itself fail to
    encode, turning a clean 422 into a 500. Only the echoed value changes: NaN becomes
    the string "nan", and every other value is untouched.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """422 with the same body shape FastAPI produces by default.

    The frontend's parseError (frontend/lib/api.ts) reads a 422 as a list under
    "detail" with "loc" and "msg" per item — that contract is preserved exactly; this
    only makes non-finite echoed inputs encodable.
    """
    return JSONResponse(
        status_code=422,
        content={"detail": _json_safe(jsonable_encoder(exc.errors()))},
    )


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
