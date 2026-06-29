"""
Remote Work Insider — main FastAPI application entry point.

Run locally:
    pip install fastapi uvicorn sqlalchemy jinja2 pydantic[email]
    python -m uvicorn main:app --reload

For Render deployment:
    - Set DATABASE_URL env var to your PostgreSQL connection string in database.py
    - Add a build command: pip install -r requirements.txt
    - Start command: uvicorn main:app --host 0.0.0.0 --port $PORT
"""

import os
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
import schemas
from database import get_db, init_db

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Remote Work Insider",
    description="Job board, applicant tracking, referral network, and writers' corner.",
    version="1.0.0",
)

# CORS — allow all origins for local dev; tighten in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict to your domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Jinja2 templates directory
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Startup: create tables
# ---------------------------------------------------------------------------

@app.on_event("startup")
def on_startup():
    """Create all DB tables on first run. Safe to call on every restart."""
    init_db()


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _get_user_or_404(user_id: int, db: Session) -> models.User:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found.")
    return user


def _get_job_or_404(job_id: int, db: Session) -> models.Job:
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return job


# ---------------------------------------------------------------------------
# Page route — server-side rendered
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, tags=["pages"])
def index(request: Request, db: Session = Depends(get_db)):
    """
    Render the unified single-page application shell.
    Initial data (jobs, blog posts) is injected server-side so the page works
    without JavaScript and search engines can crawl it.
    """
    jobs = db.query(models.Job).order_by(models.Job.created_at.desc()).limit(50).all()
    blog_posts = (
        db.query(models.BlogPost)
        .order_by(models.BlogPost.created_at.desc())
        .limit(20)
        .all()
    )

    # Enrich blog posts with author name
    enriched_posts = []
    for post in blog_posts:
        author_name = post.author.name if post.author else "Anonymous"
        enriched_posts.append(
            {
                "id": post.id,
                "title": post.title,
                "content": post.content,
                "sample_url": post.sample_url,
                "author_name": author_name,
                "author_id": post.author_id,
                "created_at": post.created_at,
            }
        )

    counts = {
        "jobs": db.query(models.Job).count(),
        "users": db.query(models.User).count(),
        "applications": db.query(models.Application).count(),
        "posts": db.query(models.BlogPost).count(),
    }

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "jobs": jobs,
            "blog_posts": enriched_posts,
            "counts": counts,
        },
    )


# ---------------------------------------------------------------------------
# User routes
# ---------------------------------------------------------------------------

@app.post(
    "/register",
    response_model=schemas.UserRead,
    status_code=status.HTTP_201_CREATED,
    tags=["users"],
)
def register_user(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user.

    - Email must be globally unique.
    - referrer_id, if provided, must reference an existing user.
    - TODO: Add password hashing and JWT issuance here for auth extension.
    """
    # Validate referrer exists
    if payload.referrer_id is not None:
        referrer = db.query(models.User).filter(
            models.User.id == payload.referrer_id
        ).first()
        if not referrer:
            raise HTTPException(
                status_code=400,
                detail=f"Referrer with id {payload.referrer_id} does not exist.",
            )

    user = models.User(
        name=payload.name,
        email=payload.email,
        role=payload.role,
        referrer_id=payload.referrer_id,
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Email '{payload.email}' is already registered.",
        )
    return user


@app.get("/users", response_model=List[schemas.UserRead], tags=["users"])
def list_users(db: Session = Depends(get_db)):
    """Return all registered users. Restrict to admin role in production."""
    return db.query(models.User).order_by(models.User.created_at.desc()).all()


# ---------------------------------------------------------------------------
# Job routes
# ---------------------------------------------------------------------------

@app.post(
    "/jobs",
    response_model=schemas.JobRead,
    status_code=status.HTTP_201_CREATED,
    tags=["jobs"],
)
def create_job(payload: schemas.JobCreate, db: Session = Depends(get_db)):
    """
    Post a new job listing.

    - posted_by_id, if provided, must reference a user with role 'employer'.
    - TODO: Enforce that only authenticated employers can post (add auth middleware).
    """
    if payload.posted_by_id is not None:
        employer = _get_user_or_404(payload.posted_by_id, db)
        if employer.role != "employer":
            raise HTTPException(
                status_code=400,
                detail=f"User {payload.posted_by_id} is not an employer (role={employer.role!r}).",
            )

    job = models.Job(
        title=payload.title,
        company=payload.company,
        description=payload.description,
        requirements=payload.requirements,
        contact_email=payload.contact_email,
        posted_by_id=payload.posted_by_id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@app.get("/jobs", response_model=List[schemas.JobRead], tags=["jobs"])
def list_jobs(db: Session = Depends(get_db)):
    """Return all active job listings ordered by most recent."""
    return db.query(models.Job).order_by(models.Job.created_at.desc()).all()


@app.get("/jobs/{job_id}", response_model=schemas.JobRead, tags=["jobs"])
def get_job(job_id: int, db: Session = Depends(get_db)):
    return _get_job_or_404(job_id, db)


# ---------------------------------------------------------------------------
# Application routes
# ---------------------------------------------------------------------------

@app.post(
    "/jobs/{job_id}/apply",
    response_model=schemas.ApplicationRead,
    status_code=status.HTTP_201_CREATED,
    tags=["applications"],
)
def apply_to_job(
    job_id: int,
    payload: schemas.ApplicationCreate,
    db: Session = Depends(get_db),
):
    """
    Submit a job application.

    Business rules:
    - The job must exist.
    - The applicant (user_id) must exist.
    - Applicant role must be 'job_seeker' or 'writer' (writers can seek contract work).
    - Duplicate applications (same job + user) are rejected with HTTP 400.
    - applied_at is set to UTC now — this timestamp is the placement audit anchor.
    """
    _get_job_or_404(job_id, db)

    applicant = _get_user_or_404(payload.user_id, db)
    if applicant.role not in ("job_seeker", "writer"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"User role '{applicant.role}' cannot apply to jobs. "
                "Only 'job_seeker' or 'writer' roles may apply."
            ),
        )

    # Check for duplicate
    existing = (
        db.query(models.Application)
        .filter(
            models.Application.job_id == job_id,
            models.Application.user_id == payload.user_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"User {payload.user_id} has already applied to job {job_id}.",
        )

    application = models.Application(
        job_id=job_id,
        user_id=payload.user_id,
        status="pending",
    )
    db.add(application)
    try:
        db.commit()
        db.refresh(application)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Duplicate application detected.",
        )
    return application


@app.post(
    "/applications/{application_id}/status",
    response_model=schemas.ApplicationRead,
    tags=["applications"],
)
def update_application_status(
    application_id: int,
    payload: schemas.ApplicationStatusUpdate,
    db: Session = Depends(get_db),
):
    """
    Transition an application's lifecycle status.

    Allowed transitions:
      pending  -> secured | closed
      secured  -> closed
      closed   -> (terminal — no further transitions)

    TODO: Add role-based authorization so only the employer who posted the job
    can mark applications as 'secured' (placement confirmed for fee collection).
    """
    app_obj = (
        db.query(models.Application)
        .filter(models.Application.id == application_id)
        .first()
    )
    if not app_obj:
        raise HTTPException(
            status_code=404, detail=f"Application {application_id} not found."
        )

    current = app_obj.status
    new = payload.status

    # Enforce allowed transitions
    allowed_transitions = {
        "pending": {"secured", "closed"},
        "secured": {"closed"},
        "closed": set(),
    }
    if new not in allowed_transitions.get(current, set()):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot transition application from '{current}' to '{new}'. "
                f"Allowed: {sorted(allowed_transitions.get(current, set()))}."
            ),
        )

    app_obj.status = new
    db.commit()
    db.refresh(app_obj)
    return app_obj


@app.get(
    "/applications",
    response_model=List[schemas.ApplicationRead],
    tags=["applications"],
)
def list_applications(
    job_id: Optional[int] = None,
    user_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Return applications filtered by any combination of job_id, user_id, status.
    Used by employers to review applicants and by the platform to audit placements.
    """
    query = db.query(models.Application)
    if job_id is not None:
        query = query.filter(models.Application.job_id == job_id)
    if user_id is not None:
        query = query.filter(models.Application.user_id == user_id)
    if status is not None:
        if status not in schemas.VALID_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status filter. Must be one of {sorted(schemas.VALID_STATUSES)}.",
            )
        query = query.filter(models.Application.status == status)

    return query.order_by(models.Application.applied_at.desc()).all()


# ---------------------------------------------------------------------------
# Blog routes
# ---------------------------------------------------------------------------

@app.get("/blog", response_model=List[schemas.BlogPostRead], tags=["blog"])
def list_blog_posts(db: Session = Depends(get_db)):
    """Return all published blog posts ordered by most recent."""
    return (
        db.query(models.BlogPost)
        .order_by(models.BlogPost.created_at.desc())
        .all()
    )


@app.post(
    "/blog",
    response_model=schemas.BlogPostRead,
    status_code=status.HTTP_201_CREATED,
    tags=["blog"],
)
def create_blog_post(payload: schemas.BlogPostCreate, db: Session = Depends(get_db)):
    """
    Submit a new blog post.

    - author_id must reference an existing user.
    - Allowed roles for authoring: 'writer' or 'job_seeker' (job seekers may share
      career stories — tighten to 'writer' only if desired).
    - TODO: Add content moderation / approval workflow before publishing.
    """
    author = _get_user_or_404(payload.author_id, db)
    if author.role not in ("writer", "job_seeker", "referrer"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"User role '{author.role}' is not permitted to publish blog posts. "
                "Allowed roles: writer, job_seeker, referrer."
            ),
        )

    post = models.BlogPost(
        author_id=payload.author_id,
        title=payload.title,
        content=payload.content,
        sample_url=payload.sample_url,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post
