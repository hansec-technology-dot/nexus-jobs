from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

VALID_ROLES = {"job_seeker", "employer", "writer", "referrer"}


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    role: str = "job_seeker"
    referrer_id: Optional[int] = None

    @field_validator("role")
    @classmethod
    def role_must_be_valid(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError(f"role must be one of {sorted(VALID_ROLES)}")
        return v


class UserRead(BaseModel):
    id: int
    name: str
    email: str
    role: str
    referrer_id: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------


class JobCreate(BaseModel):
    title: str
    company: str
    description: str
    requirements: Optional[str] = None
    contact_email: EmailStr
    posted_by_id: Optional[int] = None


class JobRead(BaseModel):
    id: int
    title: str
    company: str
    description: str
    requirements: Optional[str] = None
    contact_email: str
    posted_by_id: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

VALID_STATUSES = {"pending", "secured", "closed"}


class ApplicationCreate(BaseModel):
    job_id: int
    user_id: int


class ApplicationStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}")
        return v


class ApplicationRead(BaseModel):
    id: int
    job_id: int
    user_id: int
    status: str
    applied_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# BlogPost
# ---------------------------------------------------------------------------


class BlogPostCreate(BaseModel):
    author_id: int
    title: str
    content: str
    sample_url: Optional[str] = None


class BlogPostRead(BaseModel):
    id: int
    author_id: int
    title: str
    content: str
    sample_url: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Misc response helpers
# ---------------------------------------------------------------------------


class MessageResponse(BaseModel):
    message: str
