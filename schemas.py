"""
Pydantic schemas for request validation and response serialization.

Naming convention:
  <Model>Create  — used for POST request bodies
  <Model>Read    — used for GET/POST response bodies (includes DB-generated fields)

All Read schemas set model_config with from_attributes=True (Pydantic v2) so
FastAPI can serialize SQLAlchemy ORM objects directly.

NOTE: If you are on Pydantic v1, replace `model_config = ConfigDict(from_attributes=True)`
with `class Config: orm_mode = True` in each Read schema.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

VALID_ROLES = {"job_seeker", "employer", "writer", "referrer"}
VALID_STATUSES = {"pending", "secured", "closed"}


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    role: str
    referrer_id: Optional[int] = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError(f"role must be one of {sorted(VALID_ROLES)}")
        return v


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: str
    referrer_id: Optional[int] = None
    created_at: datetime


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
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    company: str
    description: str
    requirements: Optional[str] = None
    contact_email: str
    posted_by_id: Optional[int] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


class ApplicationCreate(BaseModel):
    job_id: int
    user_id: int


class ApplicationStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}")
        return v


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    user_id: int
    status: str
    applied_at: datetime


# ---------------------------------------------------------------------------
# BlogPost
# ---------------------------------------------------------------------------


class BlogPostCreate(BaseModel):
    author_id: int
    title: str
    content: str
    sample_url: Optional[str] = None


class BlogPostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    author_id: Optional[int] = None
    title: str
    content: str
    sample_url: Optional[str] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Composite / convenience schemas
# ---------------------------------------------------------------------------


class BlogPostReadWithAuthor(BlogPostRead):
    """Extended read schema that nests author name for template rendering."""

    author_name: Optional[str] = None


class JobReadWithApplicationCount(JobRead):
    """Extended read schema with application count for dashboard views."""

    application_count: int = 0
