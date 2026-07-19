from collections.abc import Sequence
from typing import Any

from aiogram.types import User as TelegramUser
from sqlalchemy import Select, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import SubmissionStatus, UserRole, UserState
from app.models import AuditEvent, Submission, User
from app.utils import new_submission_id


async def upsert_user(
    session: AsyncSession,
    telegram_user: TelegramUser,
    admin_id: int,
) -> User:
    user = await session.get(User, telegram_user.id)
    forced_role = UserRole.ADMIN.value if admin_id and telegram_user.id == admin_id else None
    if user is None:
        user = User(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            full_name=telegram_user.full_name,
            role=forced_role,
            active=True,
        )
        session.add(user)
    else:
        user.username = telegram_user.username
        user.full_name = telegram_user.full_name
        user.active = True
        if forced_role:
            user.role = forced_role
    await session.flush()
    return user


async def get_user(session: AsyncSession, telegram_id: int) -> User | None:
    return await session.get(User, telegram_id)


def is_authorized(user: User | None) -> bool:
    return bool(user and user.active and user.role in {role.value for role in UserRole})


def is_editor(user: User | None) -> bool:
    return bool(
        user
        and user.active
        and user.role in {UserRole.ADMIN.value, UserRole.EDITOR.value}
    )


def is_admin(user: User | None) -> bool:
    return bool(user and user.active and user.role == UserRole.ADMIN.value)


async def create_submission(session: AsyncSession, user: User) -> Submission:
    submission = Submission(
        id=new_submission_id(),
        author_id=user.telegram_id,
        author_role=user.role or UserRole.VOLUNTEER.value,
        status=SubmissionStatus.COLLECTING.value,
    )
    session.add(submission)
    await session.flush()
    await audit(session, user.telegram_id, submission.id, "submission_created")
    return submission


async def get_submission(
    session: AsyncSession,
    submission_id: str,
    *,
    for_update: bool = False,
) -> Submission | None:
    query: Select[tuple[Submission]] = select(Submission).where(Submission.id == submission_id)
    if for_update:
        query = query.with_for_update()
    return await session.scalar(query)


async def get_collecting_submission(
    session: AsyncSession,
    author_id: int,
) -> Submission | None:
    return await session.scalar(
        select(Submission)
        .where(
            Submission.author_id == author_id,
            Submission.status == SubmissionStatus.COLLECTING.value,
        )
        .order_by(desc(Submission.created_at))
        .limit(1)
    )


async def get_or_create_collecting(
    session: AsyncSession,
    user: User,
) -> Submission:
    submission = await get_collecting_submission(session, user.telegram_id)
    return submission or await create_submission(session, user)


async def list_user_submissions(
    session: AsyncSession,
    author_id: int,
    limit: int = 10,
) -> Sequence[Submission]:
    result = await session.scalars(
        select(Submission)
        .where(Submission.author_id == author_id)
        .order_by(desc(Submission.created_at))
        .limit(limit)
    )
    return result.all()


async def list_editor_ids(session: AsyncSession, admin_id: int) -> list[int]:
    result = await session.scalars(
        select(User.telegram_id).where(
            User.active.is_(True),
            User.role.in_([UserRole.ADMIN.value, UserRole.EDITOR.value]),
        )
    )
    ids = set(result.all())
    if admin_id:
        ids.add(admin_id)
    return sorted(ids)


async def list_team(session: AsyncSession) -> Sequence[User]:
    result = await session.scalars(
        select(User)
        .where(User.role.is_not(None))
        .order_by(User.role.asc(), User.telegram_id.asc())
    )
    return result.all()


async def set_role(
    session: AsyncSession,
    telegram_id: int,
    role: UserRole,
) -> User:
    user = await session.get(User, telegram_id)
    if user is None:
        user = User(
            telegram_id=telegram_id,
            full_name=f"Telegram ID {telegram_id}",
            role=role.value,
            active=True,
        )
        session.add(user)
    else:
        user.role = role.value
        user.active = True
    await session.flush()
    return user


async def revoke_role(session: AsyncSession, telegram_id: int) -> User | None:
    user = await session.get(User, telegram_id)
    if user:
        user.role = None
        user.active = False
        user.state = UserState.IDLE.value
        user.state_data = {}
        await session.flush()
    return user


async def set_user_state(
    session: AsyncSession,
    user: User,
    state: UserState,
    data: dict[str, Any] | None = None,
) -> None:
    user.state = state.value
    user.state_data = data or {}
    await session.flush()


async def audit(
    session: AsyncSession,
    actor_id: int | None,
    submission_id: str | None,
    action: str,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEvent(
            actor_id=actor_id,
            submission_id=submission_id,
            action=action,
            details=details or {},
        )
    )
    await session.flush()

