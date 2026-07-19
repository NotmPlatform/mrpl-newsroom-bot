from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.enums import SubmissionStatus, UserRole, UserState


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=False,
    )
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(160), default="")
    role: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(default=True)
    state: Mapped[str] = mapped_column(String(40), default=UserState.IDLE.value)
    state_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    submissions: Mapped[list["Submission"]] = relationship(back_populates="author")

    @property
    def role_enum(self) -> UserRole | None:
        return UserRole(self.role) if self.role else None


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"), index=True)
    author_role: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(
        String(32), default=SubmissionStatus.COLLECTING.value, index=True
    )
    raw_text: Mapped[str] = mapped_column(Text, default="")
    transcript: Mapped[str] = mapped_column(Text, default="")
    voice_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    voice_duration: Mapped[int] = mapped_column(Integer, default=0)
    telegram_photos: Mapped[list[str]] = mapped_column(JSON, default=list)
    media_group_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    ai_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    wp_media_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    wp_post_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    wp_edit_url: Mapped[str] = mapped_column(Text, default="")
    wp_preview_url: Mapped[str] = mapped_column(Text, default="")
    wp_public_url: Mapped[str] = mapped_column(Text, default="")
    rejection_comment: Mapped[str] = mapped_column(Text, default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    author: Mapped[User] = relationship(back_populates="submissions")

    @property
    def status_enum(self) -> SubmissionStatus:
        return SubmissionStatus(self.status)

    @property
    def author_role_enum(self) -> UserRole:
        return UserRole(self.author_role)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    submission_id: Mapped[str | None] = mapped_column(
        ForeignKey("submissions.id"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(80), index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


Index("ix_submissions_author_status", Submission.author_id, Submission.status)
