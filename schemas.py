from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator, model_validator

from models import ApplicationStatus, JobStatus, UserRole


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

class TimestampMixin(BaseModel):
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# User Schemas
# ---------------------------------------------------------------------------

class UserRegister(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    role: UserRole
    referral_token: Optional[str] = Field(None, description="Referral token from an existing referrer")

    @field_validator("full_name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("full_name must not be blank")
        return v.strip()


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class UserPublic(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    role: UserRole
    is_active: bool
    avatar_url: Optional[str] = None
    created_at: datetime
    referred_by_id: Optional[int] = None

    model_config = {"from_attributes": True}


class UserWithToken(BaseModel):
    user: UserPublic
    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# Seeker Profile Schemas
# ---------------------------------------------------------------------------

class SeekerProfileCreate(BaseModel):
    headline: Optional[str] = Field(None, max_length=200)
    bio: Optional[str] = None
    skills: Optional[str] = None  # comma-separated
    resume_url: Optional[str] = None
    location: Optional[str] = Field(None, max_length=120)
    years_of_experience: Optional[int] = Field(None, ge=0, le=60)
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    is_open_to_work: bool = True


class SeekerProfileUpdate(SeekerProfileCreate):
    pass


class SeekerProfilePublic(SeekerProfileCreate, TimestampMixin):
    id: int
    user_id: int


# ---------------------------------------------------------------------------
# Employer Profile Schemas
# ---------------------------------------------------------------------------

class EmployerProfileCreate(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=200)
    company_description: Optional[str] = None
    company_website: Optional[str] = None
    company_size: Optional[str] = Field(None, max_length=50)
    industry: Optional[str] = Field(None, max_length=120)
    logo_url: Optional[str] = None
    headquarters: Optional[str] = Field(None, max_length=120)
    founded_year: Optional[int] = Field(None, ge=1800, le=2100)


class EmployerProfileUpdate(EmployerProfileCreate):
    company_name: str = Field("", min_length=0, max_length=200)


class EmployerProfilePublic(EmployerProfileCreate, TimestampMixin):
    id: int
    user_id: int


# ---------------------------------------------------------------------------
# Job Schemas
# ---------------------------------------------------------------------------

class JobCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=10)
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None
    location: Optional[str] = Field(None, max_length=120)
    is_remote: bool = False
    job_type: Optional[str] = Field(None, pattern=r"^(full-time|part-time|contract|internship|freelance)$")
    salary_min: Optional[int] = Field(None, ge=0)
    salary_max: Optional[int] = Field(None, ge=0)
    salary_currency: str = Field("USD", max_length=10)
    experience_level: Optional[str] = Field(
        None, pattern=r"^(entry|junior|mid|senior|lead|executive)$"
    )
    skills_required: Optional[str] = None
    status: JobStatus = JobStatus.open
    expires_at: Optional[datetime] = None

    @model_validator(mode="after")
    def salary_range_must_be_valid(self) -> "JobCreate":
        if self.salary_min is not None and self.salary_max is not None:
            if self.salary_max < self.salary_min:
                raise ValueError("salary_max must be >= salary_min")
        return self


class JobUpdate(JobCreate):
    title: str = Field("", min_length=0, max_length=200)
    description: str = Field("", min_length=0)


class EmployerSnippet(BaseModel):
    id: int
    full_name: str
    employer_profile: Optional[EmployerProfilePublic] = None

    model_config = {"from_attributes": True}


class JobPublic(JobCreate, TimestampMixin):
    id: int
    employer_id: int
    updated_at: datetime
    employer: Optional[EmployerSnippet] = None
    application_count: Optional[int] = None

    model_config = {"from_attributes": True}


class JobList(BaseModel):
    total: int
    page: int
    page_size: int
    results: list[JobPublic]


# ---------------------------------------------------------------------------
# Application Schemas
# ---------------------------------------------------------------------------

class ApplicationCreate(BaseModel):
    cover_letter: Optional[str] = Field(None, max_length=5000)


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus


class ApplicantSnippet(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    seeker_profile: Optional[SeekerProfilePublic] = None

    model_config = {"from_attributes": True}


class ApplicationPublic(BaseModel):
    id: int
    job_id: int
    applicant_id: int
    cover_letter: Optional[str] = None
    status: ApplicationStatus
    applied_at: datetime
    updated_at: datetime
    applicant: Optional[ApplicantSnippet] = None
    job: Optional[JobPublic] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Referral Schemas
# ---------------------------------------------------------------------------

class ReferralTokenPublic(BaseModel):
    token: str
    referral_link: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ReferralStats(BaseModel):
    total_referrals: int
    seekers_referred: int
    employers_referred: int
    referrers_referred: int
    referrals: list[UserPublic]


# ---------------------------------------------------------------------------
# Generic Response
# ---------------------------------------------------------------------------

class MessageResponse(BaseModel):
    message: str
    detail: Optional[str] = None
