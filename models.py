from datetime import datetime, timezone
import enum
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class UserRole(str, enum.Enum):
    seeker = "seeker"
    employer = "employer"
    referrer = "referrer"


class JobStatus(str, enum.Enum):
    open = "open"
    closed = "closed"
    draft = "draft"


class ApplicationStatus(str, enum.Enum):
    pending = "pending"
    reviewed = "reviewed"
    shortlisted = "shortlisted"
    rejected = "rejected"
    hired = "hired"


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    avatar_url: Mapped[str] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Self-referencing referral: who brought this user in?
    referred_by_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # --- Relationships ---
    referred_by: Mapped["User"] = relationship(
        "User",
        remote_side="User.id",
        back_populates="referrals",
        foreign_keys=[referred_by_id],
    )
    referrals: Mapped[list["User"]] = relationship(
        "User",
        back_populates="referred_by",
        foreign_keys=[referred_by_id],
    )

    seeker_profile: Mapped["SeekerProfile"] = relationship(
        "SeekerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    employer_profile: Mapped["EmployerProfile"] = relationship(
        "EmployerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    posted_jobs: Mapped[list["Job"]] = relationship(
        "Job", back_populates="employer", cascade="all, delete-orphan"
    )

    applications: Mapped[list["Application"]] = relationship(
        "Application", back_populates="applicant", cascade="all, delete-orphan"
    )

    referral_token: Mapped["ReferralToken"] = relationship(
        "ReferralToken", back_populates="owner", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"


# ---------------------------------------------------------------------------
# Seeker Profile
# ---------------------------------------------------------------------------

class SeekerProfile(Base):
    __tablename__ = "seeker_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    headline: Mapped[str] = mapped_column(String(200), nullable=True)
    bio: Mapped[str] = mapped_column(Text, nullable=True)
    skills: Mapped[str] = mapped_column(Text, nullable=True)
    resume_url: Mapped[str] = mapped_column(String(512), nullable=True)
    location: Mapped[str] = mapped_column(String(120), nullable=True)
    years_of_experience: Mapped[int] = mapped_column(Integer, nullable=True)
    linkedin_url: Mapped[str] = mapped_column(String(512), nullable=True)
    github_url: Mapped[str] = mapped_column(String(512), nullable=True)
    portfolio_url: Mapped[str] = mapped_column(String(512), nullable=True)
    is_open_to_work: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="seeker_profile")


# ---------------------------------------------------------------------------
# Employer Profile
# ---------------------------------------------------------------------------

class EmployerProfile(Base):
    __tablename__ = "employer_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    company_description: Mapped[str] = mapped_column(Text, nullable=True)
    company_website: Mapped[str] = mapped_column(String(512), nullable=True)
    company_size: Mapped[str] = mapped_column(String(50), nullable=True)
    industry: Mapped[str] = mapped_column(String(120), nullable=True)
    logo_url: Mapped[str] = mapped_column(String(512), nullable=True)
    headquarters: Mapped[str] = mapped_column(String(120), nullable=True)
    founded_year: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="employer_profile")


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------

class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requirements: Mapped[str] = mapped_column(Text, nullable=True)
    responsibilities: Mapped[str] = mapped_column(Text, nullable=True)
    location: Mapped[str] = mapped_column(String(120), nullable=True)
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    job_type: Mapped[str] = mapped_column(String(50), nullable=True)
    salary_min: Mapped[int] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int] = mapped_column(Integer, nullable=True)
    salary_currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    experience_level: Mapped[str] = mapped_column(String(50), nullable=True)
    skills_required: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.open, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    employer: Mapped["User"] = relationship("User", back_populates="posted_jobs")
    applications: Mapped[list["Application"]] = relationship(
        "Application", back_populates="job", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Job id={self.id} title={self.title}>"


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("job_id", "applicant_id", name="uq_application_job_applicant"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    applicant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cover_letter: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus), default=ApplicationStatus.pending, nullable=False
    )
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    job: Mapped["Job"] = relationship("Job", back_populates="applications")
    applicant: Mapped["User"] = relationship("User", back_populates="applications")

    def __repr__(self) -> str:
        return f"<Application id={self.id} job_id={self.job_id} applicant_id={self.applicant_id}>"


# ---------------------------------------------------------------------------
# Referral Token
# ---------------------------------------------------------------------------

class ReferralToken(Base):
    __tablename__ = "referral_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    owner: Mapped["User"] = relationship("User", back_populates="referral_token")

    def __repr__(self) -> str:
        return f"<ReferralToken owner_id={self.owner_id} token={self.token}>"