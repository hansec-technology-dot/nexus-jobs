"""
NexusJobs — FastAPI Backend
Run with:  uvicorn main:app --reload --port 8000
Docs at:   http://localhost:8000/docs
"""

import hashlib
import secrets
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from database import Base, engine, get_db
from models import (
    Application,
    ApplicationStatus,
    EmployerProfile,
    Job,
    JobStatus,
    ReferralToken,
    SeekerProfile,
    User,
    UserRole,
)
from schemas import (
    ApplicationCreate,
    ApplicationPublic,
    ApplicationStatusUpdate,
    EmployerProfileCreate,
    EmployerProfilePublic,
    EmployerProfileUpdate,
    JobCreate,
    JobList,
    JobPublic,
    JobUpdate,
    MessageResponse,
    ReferralStats,
    ReferralTokenPublic,
    SeekerProfileCreate,
    SeekerProfilePublic,
    SeekerProfileUpdate,
    UserPublic,
    UserRegister,
    UserWithToken,
)

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="NexusJobs API",
    description="High-performance job marketplace API powering Seekers, Employers, and Referrers.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _hash_password(password: str) -> str:
    """Simple SHA-256 hash. Replace with bcrypt/argon2 in production."""
    return hashlib.sha256(password.encode()).hexdigest()


def _verify_password(plain: str, hashed: str) -> bool:
    return _hash_password(plain) == hashed


def _get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _get_job_or_404(db: Session, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _require_role(user: User, *roles: UserRole) -> None:
    if user.role not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Action requires one of roles: {[r.value for r in roles]}",
        )


# ---------------------------------------------------------------------------
# Root / Serve HTML
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root(request: Request):
   
    return templates.TemplateResponse(request=request, name="index.html")


# ===========================================================================
# AUTH ENDPOINTS
# ===========================================================================

@app.post(
    "/api/auth/register",
    response_model=UserWithToken,
    status_code=status.HTTP_201_CREATED,
    tags=["Auth"],
    summary="Register a new user (seeker / employer / referrer)",
)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    # Duplicate email check
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    # Resolve referral token → referred_by_id
    referred_by_id: Optional[int] = None
    if payload.referral_token:
        token_row = db.scalar(
            select(ReferralToken).where(ReferralToken.token == payload.referral_token)
        )
        if not token_row:
            raise HTTPException(status_code=400, detail="Invalid referral token")
        referred_by_id = token_row.owner_id

    # Create user
    user = User(
        full_name=payload.full_name,
        email=payload.email,
        hashed_password=_hash_password(payload.password),
        role=payload.role,
        referred_by_id=referred_by_id,
    )
    db.add(user)
    db.flush()  # get user.id before commit

    # Auto-create referral token for all users so they can refer others
    ref_token = ReferralToken(
        owner_id=user.id,
        token=secrets.token_urlsafe(32),
    )
    db.add(ref_token)
    db.commit()
    db.refresh(user)

    # Synthetic JWT placeholder — replace with python-jose in production
    access_token = secrets.token_urlsafe(48)

    return UserWithToken(user=UserPublic.model_validate(user), access_token=access_token)


@app.post(
    "/api/auth/login",
    response_model=UserWithToken,
    tags=["Auth"],
    summary="Login with email + password",
)
def login(email: str, password: str, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == email))
    if not user or not _verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account deactivated")

    access_token = secrets.token_urlsafe(48)
    return UserWithToken(user=UserPublic.model_validate(user), access_token=access_token)


# ===========================================================================
# USER ENDPOINTS
# ===========================================================================

@app.get(
    "/api/users/{user_id}",
    response_model=UserPublic,
    tags=["Users"],
    summary="Get a user by ID",
)
def get_user(user_id: int, db: Session = Depends(get_db)):
    return _get_user_or_404(db, user_id)


@app.get(
    "/api/users",
    response_model=list[UserPublic],
    tags=["Users"],
    summary="List all users (admin use)",
)
def list_users(
    role: Optional[UserRole] = None,
    skip: int = 0,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    q = select(User).where(User.is_active == True)
    if role:
        q = q.where(User.role == role)
    return db.scalars(q.offset(skip).limit(limit)).all()


# ===========================================================================
# SEEKER PROFILE ENDPOINTS
# ===========================================================================

@app.post(
    "/api/users/{user_id}/seeker-profile",
    response_model=SeekerProfilePublic,
    status_code=201,
    tags=["Seeker"],
    summary="Create seeker profile",
)
def create_seeker_profile(
    user_id: int, payload: SeekerProfileCreate, db: Session = Depends(get_db)
):
    user = _get_user_or_404(db, user_id)
    _require_role(user, UserRole.seeker)
    if user.seeker_profile:
        raise HTTPException(status_code=409, detail="Seeker profile already exists")

    profile = SeekerProfile(user_id=user_id, **payload.model_dump())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@app.get(
    "/api/users/{user_id}/seeker-profile",
    response_model=SeekerProfilePublic,
    tags=["Seeker"],
    summary="Get seeker profile",
)
def get_seeker_profile(user_id: int, db: Session = Depends(get_db)):
    user = _get_user_or_404(db, user_id)
    if not user.seeker_profile:
        raise HTTPException(status_code=404, detail="Seeker profile not found")
    return user.seeker_profile


@app.put(
    "/api/users/{user_id}/seeker-profile",
    response_model=SeekerProfilePublic,
    tags=["Seeker"],
    summary="Update seeker profile",
)
def update_seeker_profile(
    user_id: int, payload: SeekerProfileUpdate, db: Session = Depends(get_db)
):
    user = _get_user_or_404(db, user_id)
    _require_role(user, UserRole.seeker)
    if not user.seeker_profile:
        raise HTTPException(status_code=404, detail="Seeker profile not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user.seeker_profile, field, value)

    db.commit()
    db.refresh(user.seeker_profile)
    return user.seeker_profile


# ===========================================================================
# EMPLOYER PROFILE ENDPOINTS
# ===========================================================================

@app.post(
    "/api/users/{user_id}/employer-profile",
    response_model=EmployerProfilePublic,
    status_code=201,
    tags=["Employer"],
    summary="Create employer profile",
)
def create_employer_profile(
    user_id: int, payload: EmployerProfileCreate, db: Session = Depends(get_db)
):
    user = _get_user_or_404(db, user_id)
    _require_role(user, UserRole.employer)
    if user.employer_profile:
        raise HTTPException(status_code=409, detail="Employer profile already exists")

    profile = EmployerProfile(user_id=user_id, **payload.model_dump())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@app.get(
    "/api/users/{user_id}/employer-profile",
    response_model=EmployerProfilePublic,
    tags=["Employer"],
)
def get_employer_profile(user_id: int, db: Session = Depends(get_db)):
    user = _get_user_or_404(db, user_id)
    if not user.employer_profile:
        raise HTTPException(status_code=404, detail="Employer profile not found")
    return user.employer_profile


# ===========================================================================
# JOB ENDPOINTS
# ===========================================================================

@app.post(
    "/api/jobs",
    response_model=JobPublic,
    status_code=201,
    tags=["Jobs"],
    summary="Post a new job (employer only)",
)
def create_job(
    employer_id: int,
    payload: JobCreate,
    db: Session = Depends(get_db),
):
    employer = _get_user_or_404(db, employer_id)
    _require_role(employer, UserRole.employer)

    job = Job(employer_id=employer_id, **payload.model_dump())
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@app.get(
    "/api/jobs",
    response_model=JobList,
    tags=["Jobs"],
    summary="Browse / search open jobs",
)
def list_jobs(
    q: Optional[str] = Query(None, description="Search title or description"),
    location: Optional[str] = None,
    is_remote: Optional[bool] = None,
    job_type: Optional[str] = None,
    experience_level: Optional[str] = None,
    status: Optional[JobStatus] = JobStatus.open,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, le=100),
    db: Session = Depends(get_db),
):
    base_q = (
        select(Job)
        .options(
            selectinload(Job.employer).selectinload(User.employer_profile)
        )
    )

    if status:
        base_q = base_q.where(Job.status == status)
    if q:
        like = f"%{q}%"
        base_q = base_q.where(
            Job.title.ilike(like) | Job.description.ilike(like)
        )
    if location:
        base_q = base_q.where(Job.location.ilike(f"%{location}%"))
    if is_remote is not None:
        base_q = base_q.where(Job.is_remote == is_remote)
    if job_type:
        base_q = base_q.where(Job.job_type == job_type)
    if experience_level:
        base_q = base_q.where(Job.experience_level == experience_level)

    total = db.scalar(select(func.count()).select_from(base_q.subquery()))
    jobs = db.scalars(
        base_q.order_by(Job.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    # Annotate application counts
    job_ids = [j.id for j in jobs]
    count_rows = db.execute(
        select(Application.job_id, func.count(Application.id).label("cnt"))
        .where(Application.job_id.in_(job_ids))
        .group_by(Application.job_id)
    ).all()
    count_map = {r.job_id: r.cnt for r in count_rows}

    results = []
    for job in jobs:
        pj = JobPublic.model_validate(job)
        pj.application_count = count_map.get(job.id, 0)
        results.append(pj)

    return JobList(total=total or 0, page=page, page_size=page_size, results=results)


@app.get(
    "/api/jobs/{job_id}",
    response_model=JobPublic,
    tags=["Jobs"],
    summary="Get a single job by ID",
)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = (
        db.scalar(
            select(Job)
            .options(selectinload(Job.employer).selectinload(User.employer_profile))
            .where(Job.id == job_id)
        )
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.put(
    "/api/jobs/{job_id}",
    response_model=JobPublic,
    tags=["Jobs"],
    summary="Update a job listing",
)
def update_job(
    job_id: int,
    employer_id: int,
    payload: JobUpdate,
    db: Session = Depends(get_db),
):
    job = _get_job_or_404(db, job_id)
    if job.employer_id != employer_id:
        raise HTTPException(status_code=403, detail="Not your job listing")

    for field, value in payload.model_dump(exclude_unset=True).items():
        if value != "":
            setattr(job, field, value)

    db.commit()
    db.refresh(job)
    return job


@app.delete(
    "/api/jobs/{job_id}",
    response_model=MessageResponse,
    tags=["Jobs"],
    summary="Delete a job listing",
)
def delete_job(job_id: int, employer_id: int, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    if job.employer_id != employer_id:
        raise HTTPException(status_code=403, detail="Not your job listing")
    db.delete(job)
    db.commit()
    return MessageResponse(message="Job deleted successfully")


@app.get(
    "/api/employers/{employer_id}/jobs",
    response_model=list[JobPublic],
    tags=["Jobs"],
    summary="Get all jobs posted by an employer",
)
def get_employer_jobs(employer_id: int, db: Session = Depends(get_db)):
    employer = _get_user_or_404(db, employer_id)
    _require_role(employer, UserRole.employer)
    jobs = db.scalars(
        select(Job).where(Job.employer_id == employer_id).order_by(Job.created_at.desc())
    ).all()
    return jobs


# ===========================================================================
# APPLICATION ENDPOINTS
# ===========================================================================

@app.post(
    "/api/jobs/{job_id}/apply",
    response_model=ApplicationPublic,
    status_code=201,
    tags=["Applications"],
    summary="Apply for a job (seeker only)",
)
def apply_for_job(
    job_id: int,
    applicant_id: int,
    payload: ApplicationCreate,
    db: Session = Depends(get_db),
):
    seeker = _get_user_or_404(db, applicant_id)
    _require_role(seeker, UserRole.seeker)

    job = _get_job_or_404(db, job_id)
    if job.status != JobStatus.open:
        raise HTTPException(status_code=400, detail="This job is no longer accepting applications")

    # Check duplicate
    existing = db.scalar(
        select(Application).where(
            Application.job_id == job_id, Application.applicant_id == applicant_id
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="You have already applied for this job")

    app_obj = Application(
        job_id=job_id,
        applicant_id=applicant_id,
        cover_letter=payload.cover_letter,
    )
    db.add(app_obj)
    db.commit()
    db.refresh(app_obj)
    return app_obj


@app.get(
    "/api/jobs/{job_id}/applications",
    response_model=list[ApplicationPublic],
    tags=["Applications"],
    summary="Get all applications for a job (employer only)",
)
def get_job_applications(
    job_id: int,
    employer_id: int,
    db: Session = Depends(get_db),
):
    job = _get_job_or_404(db, job_id)
    if job.employer_id != employer_id:
        raise HTTPException(status_code=403, detail="Not your job listing")

    apps = db.scalars(
        select(Application)
        .options(
            selectinload(Application.applicant).selectinload(User.seeker_profile)
        )
        .where(Application.job_id == job_id)
        .order_by(Application.applied_at.desc())
    ).all()
    return apps


@app.get(
    "/api/seekers/{seeker_id}/applications",
    response_model=list[ApplicationPublic],
    tags=["Applications"],
    summary="Get all applications submitted by a seeker",
)
def get_seeker_applications(seeker_id: int, db: Session = Depends(get_db)):
    seeker = _get_user_or_404(db, seeker_id)
    _require_role(seeker, UserRole.seeker)

    apps = db.scalars(
        select(Application)
        .options(selectinload(Application.job))
        .where(Application.applicant_id == seeker_id)
        .order_by(Application.applied_at.desc())
    ).all()
    return apps


@app.patch(
    "/api/applications/{application_id}/status",
    response_model=ApplicationPublic,
    tags=["Applications"],
    summary="Update application status (employer only)",
)
def update_application_status(
    application_id: int,
    employer_id: int,
    payload: ApplicationStatusUpdate,
    db: Session = Depends(get_db),
):
    app_obj = db.get(Application, application_id)
    if not app_obj:
        raise HTTPException(status_code=404, detail="Application not found")

    job = _get_job_or_404(db, app_obj.job_id)
    if job.employer_id != employer_id:
        raise HTTPException(status_code=403, detail="Not your job listing")

    app_obj.status = payload.status
    db.commit()
    db.refresh(app_obj)
    return app_obj


# ===========================================================================
# REFERRAL ENDPOINTS
# ===========================================================================

@app.get(
    "/api/users/{user_id}/referral-token",
    response_model=ReferralTokenPublic,
    tags=["Referrals"],
    summary="Get or generate a referral token for any user",
)
def get_referral_token(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _get_user_or_404(db, user_id)

    token_row = db.scalar(select(ReferralToken).where(ReferralToken.owner_id == user_id))
    if not token_row:
        token_row = ReferralToken(owner_id=user_id, token=secrets.token_urlsafe(32))
        db.add(token_row)
        db.commit()
        db.refresh(token_row)

    base_url = str(request.base_url).rstrip("/")
    return ReferralTokenPublic(
        token=token_row.token,
        referral_link=f"{base_url}/?ref={token_row.token}",
        created_at=token_row.created_at,
    )


@app.get(
    "/api/users/{user_id}/referral-stats",
    response_model=ReferralStats,
    tags=["Referrals"],
    summary="View referral stats and all referred users",
)
def get_referral_stats(user_id: int, db: Session = Depends(get_db)):
    _get_user_or_404(db, user_id)
    referred = db.scalars(
        select(User).where(User.referred_by_id == user_id, User.is_active == True)
    ).all()

    return ReferralStats(
        total_referrals=len(referred),
        seekers_referred=sum(1 for u in referred if u.role == UserRole.seeker),
        employers_referred=sum(1 for u in referred if u.role == UserRole.employer),
        referrers_referred=sum(1 for u in referred if u.role == UserRole.referrer),
        referrals=[UserPublic.model_validate(u) for u in referred],
    )


# ===========================================================================
# STATS / DASHBOARD
# ===========================================================================

@app.get(
    "/api/stats",
    tags=["Platform"],
    summary="Platform-level stats for the homepage",
)
def platform_stats(db: Session = Depends(get_db)):
    total_users = db.scalar(select(func.count(User.id)).where(User.is_active == True)) or 0
    total_jobs = db.scalar(select(func.count(Job.id)).where(Job.status == JobStatus.open)) or 0
    total_applications = db.scalar(select(func.count(Application.id))) or 0
    total_employers = (
        db.scalar(
            select(func.count(User.id)).where(
                User.role == UserRole.employer, User.is_active == True
            )
        )
        or 0
    )
    return {
        "total_users": total_users,
        "open_jobs": total_jobs,
        "total_applications": total_applications,
        "total_employers": total_employers,
    }
