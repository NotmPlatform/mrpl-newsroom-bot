from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    EDITOR = "editor"
    VOLUNTEER = "volunteer"


class SubmissionStatus(StrEnum):
    COLLECTING = "collecting"
    GENERATING = "generating"
    SYNCING = "syncing"
    PREVIEW = "preview"
    AWAITING_EDITOR = "awaiting_editor"
    PUBLISHING = "publishing"
    REJECTED = "rejected"
    PUBLISHED = "published"
    CANCELLED = "cancelled"
    FAILED = "failed"


class UserState(StrEnum):
    IDLE = "idle"
    AWAITING_REJECTION_REASON = "awaiting_rejection_reason"
    AWAITING_COVER = "awaiting_cover"
