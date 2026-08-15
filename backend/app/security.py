import datetime as dt

import jwt

from app.config import get_settings

ALGORITHM = "HS256"


def create_token(user_id: int, org_id: int, role: str) -> str:
    settings = get_settings()
    payload = {
        "sub": str(user_id),
        "org_id": org_id,
        "role": role,
        "exp": dt.datetime.utcnow() + dt.timedelta(hours=12),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
