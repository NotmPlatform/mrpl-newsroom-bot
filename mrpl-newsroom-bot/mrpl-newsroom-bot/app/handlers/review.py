import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.enums import SubmissionStatus, UserState
from app.models import User
from app.repository import audit, get_submission, is_editor, set_user_state
from app.services.container import Services
from app.utils import escape

logger = logging.getLogger(__name__)
router = Router(name="review")


@router.callback_query(F.data.startswith("publish:"))
async def publish_submission(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    settings: Settings,
    services: Services,
) -> None:
    await callback.answer("Проверяю черновик…")
    if not is_editor(db_user):
        return
    submission_id = callback.data.split(":", 1)[1]
    submission = await get_submission(session, submission_id)
    if not submission or not submission.wp_post_id:
        await callback.message.answer("Черновик не найден.")
        return
    if submission.status == SubmissionStatus.PUBLISHED.value:
        await callback.message.answer(
            f"Новость уже опубликована:\n{escape(submission.wp_public_url)}"
        )
        return
    if submission.status not in {
        SubmissionStatus.PREVIEW.value,
        SubmissionStatus.AWAITING_EDITOR.value,
    }:
        await callback.message.answer("Материал сейчас нельзя опубликовать.")
        return
    if not settings.publish_enabled:
        await callback.message.answer(
            "Тестовый режим: публикация отключена переменной PUBLISH_ENABLED=false."
        )
        return

    previous_status = submission.status
    submission.status = SubmissionStatus.PUBLISHING.value
    await audit(session, db_user.telegram_id, submission.id, "publish_started")
    await session.commit()
    try:
        response = await services.wordpress.publish(
            submission.wp_post_id,
            submission.id,
        )
        submission.status = SubmissionStatus.PUBLISHED.value
        submission.wp_public_url = str(response.get("public_url") or "")
        submission.published_at = datetime.now(timezone.utc)
        await audit(
            session,
            db_user.telegram_id,
            submission.id,
            "submission_published",
            {"post_id": submission.wp_post_id, "url": submission.wp_public_url},
        )
        await session.commit()
    except Exception:
        logger.exception("Publication failed for %s", submission.id)
        submission.status = previous_status
        await session.commit()
        await callback.message.answer("WordPress не опубликовал новость. Попробуйте ещё раз.")
        return

    text = "Новость опубликована."
    if submission.wp_public_url:
        text += f"\n{escape(submission.wp_public_url)}"
    await callback.message.answer(text)
    if submission.author_id != db_user.telegram_id:
        try:
            await callback.bot.send_message(
                submission.author_id,
                "✅ Ваша новость опубликована.\n"
                f"{escape(submission.wp_public_url)}",
            )
        except Exception as exc:
            logger.warning("Could not notify published author: %s", exc)


@router.callback_query(F.data.startswith("reject:"))
async def request_rejection_reason(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
) -> None:
    await callback.answer()
    if not is_editor(db_user):
        return
    submission_id = callback.data.split(":", 1)[1]
    submission = await get_submission(session, submission_id)
    if (
        not submission
        or submission.status != SubmissionStatus.AWAITING_EDITOR.value
        or not submission.wp_post_id
    ):
        await callback.message.answer("Материал уже обработан или недоступен.")
        return
    await set_user_state(
        session,
        db_user,
        UserState.AWAITING_REJECTION_REASON,
        {"submission_id": submission.id},
    )
    await callback.message.answer(
        "Напишите одним сообщением, почему материал нужно доработать."
    )

