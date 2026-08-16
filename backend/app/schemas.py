from typing import Optional

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    name: str
    email: EmailStr
    role: Optional[str] = None  # required when email domain is shaily.com


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
    device: Optional[str] = None
    total: float = 0


class RequestOut(BaseModel):
    id: int
    org_id: int
    submitted_by: int
    brand: str
    market: str
    device: Optional[str]
    status: str
    total: float
    assigned_kam_id: Optional[int] = None


class KamOut(BaseModel):
    id: int
    name: str
    email: str


class OrgKamMapOut(BaseModel):
    org_id: int
    org_name: str
    kam_user_id: Optional[int] = None
    kam_name: Optional[str] = None


class OrgKamMapUpdate(BaseModel):
    kam_user_id: int


class AssignKamRequest(BaseModel):
    kam_user_id: int
