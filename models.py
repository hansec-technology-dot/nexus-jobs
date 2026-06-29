from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database import Base


def _utcnow():
    """Return current UTC datetime (timezone-naive for SQLite compatibility)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)

    # Allowed roles: job_seeker, employer, writer, referrer
    role = Column(
        String(20),
        nullable=False,
        default="job_seeker",
    )

    # Self-referencing FK: which existing user referred this user.
    # ON DELETE SET NULL: if the referrer is deleted, referrer_id becomes NULL
    # so the referred user record is preserved (important for fee traceability).
    referrer_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(DateTime, default=_utcnow, nullable=False)

    # Self-referencing relationship: one referrer -> many referred users
    referrals = relationship(
        "User",
        backref="referrer",
        foreign_keys=[referrer_id],
        lazy="select",
    )

    # Employer's posted jobs (posted_by_id -> User)
    posted_jobs = relationship(
        "Job",
        back_populates="posted_by",
        foreign_keys="Job.posted_by_id",
        lazy="select",
    )

    # Job seeker's applications
    applications = relationship(
        "Application",
        back_populates="applicant",
        cascade="all, delete-orphan",  # removing user removes their applications
        lazy="select",
    )

    # Writer's blog posts
    blog_posts = relationship(
        "BlogPost",
        back_populates="author",
        cascade="all, delete-orphan",
        lazy="select",
    )

    __table_args__ = (
        CheckConstraint(
            role.in_(["job_seeker", "employer", "writer", "referrer"]),
            name="ck_user_role",
        ),
    )


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    company = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    requirements = Column(Text, nullable=True)
    contact_email = Column(String(255), nullable=False)

    # ON DELETE SET NULL: if the employer account is deleted, the job listing
    # is preserved for historical/traceability purposes but loses its owner link.
    posted_by_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(DateTime, default=_utcnow, nullable=False)

    posted_by = relationship(
        "User",
        back_populates="posted_jobs",
        foreign_keys=[posted_by_id],
    )

    applications = relationship(
        "Application",
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="select",
    )


class Application(Base):
    """
    Business-critical model: every job application is logged here.
    Placements (fee collection) are traced via status transitions:
      pending  -> secured (placement confirmed, fee applies)
      secured  -> closed  (placement finalized / contract ended)
      pending  -> closed  (application withdrawn or rejected)

    applied_at is immutable once set (set at creation).
    """

    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)

    job_id = Column(
        Integer,
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ON DELETE CASCADE from User: if user is fully removed, their applications
    # are also removed. For stricter traceability, change to SET NULL and allow
    # nullable user_id — uncomment the block below and adjust cascade.
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    status = Column(String(10), nullable=False, default="pending")

    # applied_at is the authoritative timestamp for placement tracing.
    applied_at = Column(DateTime, default=_utcnow, nullable=False)

    job = relationship("Job", back_populates="applications")
    applicant = relationship("User", back_populates="applications")

    __table_args__ = (
        # Prevent duplicate applications from same user to same job
        UniqueConstraint("job_id", "user_id", name="uq_application_job_user"),
        CheckConstraint(
            status.in_(["pending", "secured", "closed"]),
            name="ck_application_status",
        ),
        # Indexes for fast traceability queries
        Index("ix_application_job_id", "job_id"),
        Index("ix_application_user_id", "user_id"),
        Index("ix_application_status", "status"),
    )


class BlogPost(Base):
    __tablename__ = "blog_posts"

    id = Column(Integer, primary_key=True, index=True)

    # ON DELETE CASCADE: if the author account is removed, their posts go too.
    # Change to SET NULL + nullable author_id if you want to preserve orphaned posts.
    author_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    sample_url = Column(String(512), nullable=True)  # optional portfolio/sample link
    created_at = Column(DateTime, default=_utcnow, nullable=False)

    author = relationship("User", back_populates="blog_posts")
