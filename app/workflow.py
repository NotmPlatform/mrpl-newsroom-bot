import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.enums import UserRole
from app.keyboards import editor_review_keyboard
from app.models import Submission
from app.repository import audit, list_editor_ids
from app.schemas import Article
from app.services.container import Services
from app.services.media import download_telegram_file, prepare_telegram_image
from app.utils import article_preview, escape

logger = logging.getLogger(__name__)


async def generate_article(
    bot: Bot,
    session: AsyncSession,
    submission: Submission,
    services: Services,
    settings: Settings,
    revision_note: str = "",
) -> Article:
    if submission.voice_file_id and not submission.transcript:
        voice_path = settings.temp_dir / f"{submission.id}.ogg"
        try:
            await download_telegram_file(bot, submission.voice_file_id, voice_path)
            submission.transcript = await services.speechkit.transcribe(voice_path)
            await audit(
                session,
                submission.author_id,
                submission.id,
                "voice_transcribed",
                {"characters": len(submission.transcript)},
            )
            await session.commit()
        finally:
            voice_path.unlink(missing_ok=True)

    previous = submission.ai_payload or None
    article = await services.deepseek.generate(
        raw_text=submission.raw_text,
        transcript=submission.transcript,
        previous_article=previous,
        revision_note=revision_note,
    )
    submission.ai_payload = article.model_dump(mode="json")
    submission.error_message = ""
    await audit(
        session,
        submission.author_id,
        submission.id,
        "article_generated",
        {"title": article.title},
    )
    await session.commit()
    return article


async def sync_draft_to_wordpress(
    bot: Bot,
    session: AsyncSession,
    submission: Submission,
    article: Article,
    services: Services,
    settings: Settings,
) -> dict:
    media_ids = list(submission.wp_media_ids or [])
    photo_ids = list(submission.telegram_photos or [])

    for index in range(len(media_ids), len(photo_ids)):
        prepared = await prepare_telegram_image(
            bot,
            photo_ids[index],
            settings,
            submission.id,
            index,
        )
        media_id = await services.wordpress.upload_image(prepared, article.image_alt)
        media_ids.append(media_id)
        submission.wp_media_ids = media_ids
        await audit(
            session,
            submission.author_id,
            submission.id,
            "image_uploaded",
            {"media_id": media_id, "index": index},
        )
        await session.commit()

    response = await services.wordpress.create_or_update_draft(
        submission_id=submission.id,
        telegram_author_id=submission.author_id,
        article=article,
        media_ids=media_ids,
    )
    submission.wp_post_id = int(response["id"])
    submission.wp_edit_url = str(response.get("edit_url") or "")
    submission.wp_preview_url = str(response.get("preview_url") or "")
    submission.wp_public_url = str(response.get("public_url") or "")
    await audit(
        session,
        submission.author_id,
        submission.id,
        "wordpress_draft_synced",
        {"post_id": submission.wp_post_id},
    )
    await session.commit()
    return response


async def notify_editors(
    bot: Bot,
    session: AsyncSession,
    submission: Submission,
    article: Article,
    settings: Settings,
) -> int:
    editor_ids = await list_editor_ids(session, settings.admin_telegram_id)
    text = (
        "🔔 <b>Новая новость на проверку</b>\n\n"
        f"{article_preview(article, submission.id)}\n\n"
        f"Автор: <code>{submission.author_id}</code>"
    )
    delivered = 0

    for editor_id in editor_ids:
        try:
            if submission.telegram_photos:
                await bot.send_photo(
                    editor_id,
                    submission.telegram_photos[0],
                    caption=f"📷 {escape(article.title)}",
                )
            await bot.send_message(
                editor_id,
                text,
                reply_markup=editor_review_keyboard(
                    submission.id,
                    submission.wp_edit_url,
                ),
            )
            delivered += 1
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            logger.warning("Could not notify editor %s: %s", editor_id, exc)

    await audit(
        session,
        submission.author_id,
        submission.id,
        "editors_notified",
        {"delivered": delivered, "total": len(editor_ids)},
    )
    return delivered


def can_user_manage_submission(
    telegram_id: int,
    role: str | None,
    submission: Submission,
) -> bool:
    return telegram_id == submission.author_id or role in {
        UserRole.ADMIN.value,
        UserRole.EDITOR.value,
    }
