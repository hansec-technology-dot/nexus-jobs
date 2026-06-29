from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database import Base


def _utcnow():
    """Return current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)

    # Allowed roles: job_seeker, employer, writer, referrer
    # Use a CheckConstraint so SQLite enforces it at DB level.
    role = Column(
        String(20),
        nullable=False,
        default="job_seeker",
    )

    # Self-referencing FK: tracks which existing user referred this user.
    # ON DELETE SET NULL — if the referrer is ever deleted, we lose the link
    # but keep the referred user record intact.
    referrer_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # Self-referencing relationship
    referrals = relationship(
        "User",
        backref="referrer",  # user.referrer -> the User who referred this user
        foreign_keys=[referrer_id],
        # Do NOT cascade delete; referred users survive referrer deletion.
    )

    # One user (writer/job_seeker) can author many blog posts
    blog_posts = relationship("BlogPost", back_populates="author")

    # One job_seeker user can have many applications
    applications = relationship("Application", back_populates="applicant")

    # Jobs posted by this employer
    posted_jobs = relationship("Job", back_populates="posted_by")

    __table_args__ = (
        CheckConstraint(
            "role IN ('job_seeker', 'employer', 'writer', 'referrer')",
            name="chk_user_role",
        ),
    )

    def __repr__(self):
        return f"<User id={self.id} email={self.email!r} role={self.role!r}>"


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------
class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    company = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    requirements = Column(Text, nullable=True)
    contact_email = Column(String(255), nullable=False)

    # ON DELETE SET NULL: if the employer user is deleted, the job listing
    # remains visible but loses the employer association. This preserves
    # historical job data and application traceability.
    posted_by_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # Relationships
    posted_by = relationship("User", back_populates="posted_jobs")
    applications = relationship(
        "Application",
        back_populates="job",
        cascade="all, delete-orphan",  # Deleting a job removes its applications
    )

    def __repr__(self):
        return f"<Job id={self.id} title={self.title!r} company={self.company!r}>"


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
class Application(Base):
    """
    Business-critical model: every application is permanently logged here.
    Traceability: job_id + user_id + applied_at + status forms the audit trail
    used for placement fee collection when status transitions to 'secured'.
    """

    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)

    # RESTRICT delete on job_id — do not silently lose application records.
    # In practice, deactivate jobs instead of deleting them.
    job_id = Column(
        Integer,
        ForeignKey("jobs.id", ondelete="CASCADE"),  # cascade from Job.applications above
        nullable=False,
        index=True,
    )

    # ON DELETE RESTRICT (default) — do not allow deleting a user who has
    # applications, preserving the placement audit trail.
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Lifecycle: pending -> secured (placement confirmed) or closed (rejected/withdrawn)
    status = Column(
        String(20),
        nullable=False,
        default="pending",
    )

    # Business-critical: exact UTC timestamp of application submission
    applied_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # Relationships
    job = relationship("Job", back_populates="applications")
    applicant = relationship("User", back_populates="applications")

    __table_args__ = (
        # Prevent duplicate applications from the same user to the same job
        UniqueConstraint("job_id", "user_id", name="uq_application_job_user"),
        CheckConstraint(
            "status IN ('pending', 'secured', 'closed')",
            name="chk_application_status",
        ),
    )

    def __repr__(self):
        return (
            f"<Application id={self.id} job_id={self.job_id} "
            f"user_id={self.user_id} status={self.status!r}>"
        )


# ---------------------------------------------------------------------------
# BlogPost
# ---------------------------------------------------------------------------
class BlogPost(Base):
    __tablename__ = "blog_posts"

    id = Column(Integer, primary_key=True, index=True)

    # ON DELETE SET NULL: if the author is deleted, keep the blog post
    # (editorial content should survive user account removal).
    author_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    sample_url = Column(String(512), nullable=True)  # e.g. link to published article
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    author = relationship("User", back_populates="blog_posts")

    def __repr__(self):
        return f"<BlogPost id={self.id} title={self.title!r}>"
