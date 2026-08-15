from __future__ import annotations

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    name: str
    email: EmailStr
    role: str | None = None  # required when email domain is shaily.com


class UserOut(BaseModel):
    id: int
    org_id: int
    name: str
    email: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class RequestCreate(BaseModel):
    brand: str
    market: str
    device: str | None = None
    total: float = 0


class RequestOut(BaseModel):
    id: int
    org_id: int
    submitted_by: int
    brand: str
    market: str
    device: str | None
    status: str
    total: float
