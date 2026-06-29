"""
Remote Work Insider — unified FastAPI application.
Run: uvicorn main:app --reload
Tables are created automatically on first run via init_db().

Extension points:
  - Add JWT/OAuth2 authentication by injecting a `current_user` dependency.
  - Swap SQLite URL in database.py for PostgreSQL when deploying to Render.
  - Add Alembic for schema migrations once the schema stabilises.
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
# App bootstrap
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Remote Work Insider",
    description="Unified job board, referral tracker, and writers' corner for remote workers.",
    version="1.0.0",
)

# CORS — allow all origins for local dev; restrict to your domain in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

# Create tables on startup (idempotent — safe to call repeatedly).
init_db()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_user_or_404(db: Session, user_id: int) -> models.User:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return user


def _get_job_or_404(db: Session, job_id: int) -> models.Job:
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


# ---------------------------------------------------------------------------
# Page route
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    """
    Server-side rendered landing page.
    Passes initial data to Jinja2 so the page works without JavaScript too.
    """
    jobs = db.query(models.Job).order_by(models.Job.created_at.desc()).limit(50).all()
    blog_posts = (
        db.query(models.BlogPost)
        .order_by(models.BlogPost.created_at.desc())
        .limit(50)
        .all()
    )

    # Enrich blog posts with author names for the template
    enriched_posts = []
    for post in blog_posts:
        author_name = post.author.name if post.author else "Unknown"
        enriched_posts.append(
            {
                "id": post.id,
                "title": post.title,
                "content": post.content,
                "sample_url": post.sample_url,
                "author_id": post.author_id,
                "author_name": author_name,
                "created_at": post.created_at,
            }
        )

    counts = {
        "jobs": db.query(models.Job).count(),
        "users": db.query(models.User).count(),
        "placements": db.query(models.Application)
        .filter(models.Application.status == "secured")
        .count(),
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
# Users
# ---------------------------------------------------------------------------


@app.post(
    "/register",
    response_model=schemas.UserRead,
    status_code=status.HTTP_201_CREATED,
    tags=["users"],
)
def register_user(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    """Register a new user. Email must be unique. Optional referrer_id links referral chain."""

    # Validate referrer exists if provided
    if payload.referrer_id is not None:
        referrer = db.query(models.User).filter(models.User.id == payload.referrer_id).first()
        if not referrer:
            raise HTTPException(
                status_code=400,
                detail=f"Referrer with id {payload.referrer_id} does not exist",
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
            detail=f"Email '{payload.email}' is already registered",
        )
    return user


@app.get("/users", response_model=List[schemas.UserRead], tags=["users"])
def list_users(db: Session = Depends(get_db)):
    return db.query(models.User).order_by(models.User.created_at.desc()).all()


@app.get("/users/{user_id}", response_model=schemas.UserRead, tags=["users"])
def get_user(user_id: int, db: Session = Depends(get_db)):
    return _get_user_or_404(db, user_id)


# ---------------------------------------------------------------------------
# Jobs
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
    If posted_by_id is provided it must reference a user with role='employer'.
    Extension: add authentication dependency here to auto-derive posted_by from token.
    """
    if payload.posted_by_id is not None:
        poster = _get_user_or_404(db, payload.posted_by_id)
        if poster.role != "employer":
            raise HTTPException(
                status_code=400,
                detail="Only users with role 'employer' can post jobs",
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
    return db.query(models.Job).order_by(models.Job.created_at.desc()).all()


@app.get("/jobs/{job_id}", response_model=schemas.JobRead, tags=["jobs"])
def get_job(job_id: int, db: Session = Depends(get_db)):
    return _get_job_or_404(db, job_id)


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------


@app.post(
    "/jobs/{job_id}/apply",
    response_model=schemas.ApplicationRead,
    status_code=status.HTTP_201_CREATED,
    tags=["applications"],
)
def apply_for_job(
    job_id: int,
    payload: schemas.ApplicationCreate,
    db: Session = Depends(get_db),
):
    """
    Create a job application. Validates:
    - Job exists
    - User exists and has an appropriate role (job_seeker or writer)
    - No duplicate application for the same (job, user) pair
    Business rule: applied_at is authoritative for fee/placement tracing.
    """
    _get_job_or_404(db, job_id)

    # Ensure job_id in path matches payload for consistency
    if payload.job_id != job_id:
        raise HTTPException(
            status_code=400,
            detail="job_id in URL and request body must match",
        )

    applicant = _get_user_or_404(db, payload.user_id)
    if applicant.role not in ("job_seeker", "writer"):
        raise HTTPException(
            status_code=400,
            detail=f"Users with role '{applicant.role}' cannot apply for jobs",
        )

    # Check for duplicate application
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
            detail="You have already applied for this job",
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
        raise HTTPException(status_code=400, detail="Duplicate application")
    return application


@app.patch(
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
    Transition application status.
    Allowed transitions:
      pending  -> secured | closed
      secured  -> closed
    Extension: restrict this endpoint to employer role via auth dependency.
    """
    application = (
        db.query(models.Application)
        .filter(models.Application.id == application_id)
        .first()
    )
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # Enforce allowed transitions
    allowed: dict = {
        "pending": {"secured", "closed"},
        "secured": {"closed"},
        "closed": set(),
    }
    if payload.status not in allowed.get(application.status, set()):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot transition from '{application.status}' to '{payload.status}'. "
                f"Allowed: {sorted(allowed.get(application.status, set())) or 'none'}"
            ),
        )

    application.status = payload.status
    db.commit()
    db.refresh(application)
    return application


@app.get("/applications", response_model=List[schemas.ApplicationRead], tags=["applications"])
def list_applications(
    job_id: Optional[int] = None,
    user_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List applications with optional filters for placement traceability."""
    query = db.query(models.Application)
    if job_id is not None:
        query = query.filter(models.Application.job_id == job_id)
    if user_id is not None:
        query = query.filter(models.Application.user_id == user_id)
    if status is not None:
        if status not in ("pending", "secured", "closed"):
            raise HTTPException(status_code=400, detail="Invalid status filter")
        query = query.filter(models.Application.status == status)
    return query.order_by(models.Application.applied_at.desc()).all()


# ---------------------------------------------------------------------------
# Blog
# ---------------------------------------------------------------------------


@app.get("/blog", response_model=List[schemas.BlogPostRead], tags=["blog"])
def list_blog_posts(db: Session = Depends(get_db)):
    return db.query(models.BlogPost).order_by(models.BlogPost.created_at.desc()).all()


@app.post(
    "/blog",
    response_model=schemas.BlogPostRead,
    status_code=status.HTTP_201_CREATED,
    tags=["blog"],
)
def create_blog_post(payload: schemas.BlogPostCreate, db: Session = Depends(get_db)):
    """
    Publish a blog post. Author must be a registered user.
    Writers and job_seekers may post. Extend with auth to auto-derive author.
    """
    author = _get_user_or_404(db, payload.author_id)
    if author.role not in ("writer", "job_seeker", "referrer"):
        raise HTTPException(
            status_code=400,
            detail=f"Users with role '{author.role}' cannot publish blog posts",
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
