import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.enums import SubmissionStatus, UserRole, UserState
from app.keyboards import (
    collecting_keyboard,
    confirm_revoke_keyboard,
    confirm_role_keyboard,
    editor_preview_keyboard,
    editor_review_keyboard,
    rejected_author_keyboard,
    volunteer_preview_keyboard,
)
from app.models import Submission, User
from app.repository import (
    audit,
    get_or_create_collecting,
    get_submission,
    is_admin,
    is_authorized,
    is_editor,
    set_user_state,
)
from app.schemas import Article
from app.services.container import Services
from app.services.media import prepare_telegram_image
from app.utils import article_preview, escape
from app.workflow import (
    can_user_manage_submission,
    generate_article,
    notify_editors,
    sync_draft_to_wordpress,
)

logger = logging.getLogger(__name__)
router = Router(name="submissions")


async def _get_allowed_submission(
    session: AsyncSession,
    db_user: User,
    submission_id: str,
) -> Submission | None:
    submission = await get_submission(session, submission_id)
    if not submission:
        return None
    if not can_user_manage_submission(db_user.telegram_id, db_user.role, submission):
        return None
    return submission


async def _send_preview(
    bot: Bot,
    chat_id: int,
    submission: Submission,
    article: Article,
    db_user: User,
    *,
    review_mode: bool = False,
) -> None:
    if submission.telegram_photos:
        await bot.send_photo(
            chat_id,
            submission.telegram_photos[0],
            caption=f"📷 {escape(article.title)}",
        )

    if review_mode:
        keyboard = editor_review_keyboard(submission.id, submission.wp_edit_url)
    elif is_editor(db_user):
        keyboard = editor_preview_keyboard(submission.id, submission.wp_edit_url)
    else:
        keyboard = volunteer_preview_keyboard(submission.id)

    await bot.send_message(
        chat_id,
        article_preview(article, submission.id),
        reply_markup=keyboard,
    )


async def _process_rejection_reason(
    message: Message,
    session: AsyncSession,
    db_user: User,
    services: Services,
) -> bool:
    if db_user.state != UserState.AWAITING_REJECTION_REASON.value:
        return False
    if not is_editor(db_user):
        await set_user_state(session, db_user, UserState.IDLE)
        return True

    submission_id = str((db_user.state_data or {}).get("submission_id") or "")
    submission = await get_submission(session, submission_id)
    if not submission or not submission.wp_post_id:
        await set_user_state(session, db_user, UserState.IDLE)
        await message.answer("Черновик больше не найден.")
        return True

    reason = (message.text or "").strip()
    if len(reason) < 5:
        await message.answer("Напишите понятную причину отклонения минимум из 5 символов.")
        return True

    await services.wordpress.reject(submission.wp_post_id, reason)
    submission.status = SubmissionStatus.REJECTED.value
    submission.rejection_comment = reason
    await set_user_state(session, db_user, UserState.IDLE)
    await audit(
        session,
        db_user.telegram_id,
        submission.id,
        "submission_rejected",
        {"reason": reason},
    )
    await session.commit()

    await message.answer("Материал отклонён, комментарий отправлен автору.")
    try:
        await message.bot.send_message(
            submission.author_id,
            "Редактор вернул материал на доработку.\n\n"
            f"<b>Комментарий:</b> {escape(reason)}",
            reply_markup=rejected_author_keyboard(submission.id),
        )
    except Exception as exc:
        logger.warning("Could not notify rejected author %s: %s", submission.author_id, exc)
    return True


async def _replace_cover(
    message: Message,
    session: AsyncSession,
    db_user: User,
    settings: Settings,
    services: Services,
) -> bool:
    if db_user.state != UserState.AWAITING_COVER.value:
        return False
    if not is_editor(db_user):
        await set_user_state(session, db_user, UserState.IDLE)
        return True

    submission_id = str((db_user.state_data or {}).get("submission_id") or "")
    submission = await get_submission(session, submission_id)
    if not submission or not submission.wp_post_id or not submission.ai_payload:
        await set_user_state(session, db_user, UserState.IDLE)
        await message.answer("Черновик для замены обложки не найден.")
        return True

    new_file_id = message.photo[-1].file_id
    article = Article.model_validate(submission.ai_payload)
    prepared = await prepare_telegram_image(
        message.bot,
        new_file_id,
        settings,
        submission.id,
        0,
    )
    media_id = await services.wordpress.upload_image(prepared, article.image_alt)
    submission.telegram_photos = [new_file_id] + list(submission.telegram_photos or [])
    submission.wp_media_ids = [media_id] + list(submission.wp_media_ids or [])
    response = await services.wordpress.create_or_update_draft(
        submission_id=submission.id,
        telegram_author_id=submission.author_id,
        article=article,
        media_ids=submission.wp_media_ids,
    )
    submission.wp_edit_url = str(response.get("edit_url") or submission.wp_edit_url)
    submission.wp_preview_url = str(response.get("preview_url") or submission.wp_preview_url)
    await set_user_state(session, db_user, UserState.IDLE)
    await audit(
        session,
        db_user.telegram_id,
        submission.id,
        "cover_replaced",
        {"media_id": media_id},
    )
    await session.commit()

    review_mode = submission.author_id != db_user.telegram_id
    await message.answer("Обложка заменена.")
    await _send_preview(
        message.bot,
        message.chat.id,
        submission,
        article,
        db_user,
        review_mode=review_mode,
    )
    return True


async def _process_team_member_id(
    message: Message,
    session: AsyncSession,
    db_user: User,
) -> bool:
    if db_user.state != UserState.AWAITING_TEAM_MEMBER_ID.value:
        return False
    if not is_admin(db_user):
        await set_user_state(session, db_user, UserState.IDLE)
        return True

    raw_id = (message.text or "").strip()
    try:
        telegram_id = int(raw_id)
    except ValueError:
        await message.answer(
            "Telegram ID должен состоять только из цифр. "
            "Отправьте ID ещё раз или нажмите «Отмена» в предыдущем сообщении."
        )
        return True
    if telegram_id <= 0:
        await message.answer("Telegram ID должен быть положительным числом.")
        return True

    state_data = db_user.state_data or {}
    action = str(state_data.get("action") or "")
    await set_user_state(session, db_user, UserState.IDLE)

    if action == "set_role":
        role = str(state_data.get("role") or "")
        if role not in {UserRole.EDITOR.value, UserRole.VOLUNTEER.value}:
            await message.answer("Роль не выбрана. Начните добавление сотрудника заново.")
            return True
        role_label = "редактор" if role == UserRole.EDITOR.value else "волонтёр"
        await message.answer(
            f"Назначить пользователю <code>{telegram_id}</code> "
            f"роль <b>{role_label}</b>?",
            reply_markup=confirm_role_keyboard(telegram_id, role),
        )
        return True

    if action == "revoke":
        await message.answer(
            f"Отозвать доступ у пользователя <code>{telegram_id}</code>?",
            reply_markup=confirm_revoke_keyboard(telegram_id),
        )
        return True

    await message.answer("Действие устарело. Откройте управление командой заново.")
    return True


@router.message(F.text & ~F.text.startswith("/"))
async def receive_text(
    message: Message,
    session: AsyncSession,
    db_user: User,
    services: Services,
) -> None:
    if await _process_team_member_id(message, session, db_user):
        return
    if await _process_rejection_reason(message, session, db_user, services):
        return
    if not is_authorized(db_user):
        await message.answer(f"Доступ не выдан. Ваш ID: <code>{message.from_user.id}</code>")
        return
    if db_user.state == UserState.AWAITING_COVER.value:
        await message.answer("Сейчас ожидается фотография для новой обложки.")
        return

    submission = await get_or_create_collecting(session, db_user)
    incoming = (message.text or "").strip()
    combined = "\n\n".join(filter(None, [submission.raw_text.strip(), incoming]))
    submission.raw_text = combined[:30000]
    await audit(
        session,
        db_user.telegram_id,
        submission.id,
        "text_added",
        {"characters": len(incoming)},
    )
    await message.answer(
        "Текст добавлен. Можно прислать фотографии или сформировать новость.",
        reply_markup=collecting_keyboard(submission.id),
    )


@router.message(F.photo)
async def receive_photo(
    message: Message,
    session: AsyncSession,
    db_user: User,
    settings: Settings,
    services: Services,
) -> None:
    if await _replace_cover(message, session, db_user, settings, services):
        return
    if not is_authorized(db_user):
        return

    submission = await get_or_create_collecting(session, db_user)
    photos = list(submission.telegram_photos or [])
    file_id = message.photo[-1].file_id
    if file_id not in photos:
        if len(photos) >= settings.max_photos:
            await message.answer(f"Можно добавить не больше {settings.max_photos} фотографий.")
            return
        photos.append(file_id)
        submission.telegram_photos = photos

    if message.caption:
        submission.raw_text = "\n\n".join(
            filter(None, [submission.raw_text.strip(), message.caption.strip()])
        )[:30000]

    group_id = str(message.media_group_id or "")
    groups = list(submission.media_group_ids or [])
    first_in_group = not group_id or group_id not in groups
    if group_id and group_id not in groups:
        groups.append(group_id)
        submission.media_group_ids = groups

    await audit(
        session,
        db_user.telegram_id,
        submission.id,
        "photo_added",
        {"count": len(photos), "media_group_id": group_id},
    )
    if first_in_group:
        text = (
            "Альбом получаю. После загрузки всех фотографий нажмите кнопку ниже."
            if group_id
            else f"Фотография добавлена. Всего: {len(photos)}."
        )
        await message.answer(text, reply_markup=collecting_keyboard(submission.id))


@router.message(F.voice)
async def receive_voice(
    message: Message,
    session: AsyncSession,
    db_user: User,
    settings: Settings,
) -> None:
    if not is_authorized(db_user):
        return
    duration = int(message.voice.duration or 0)
    if duration > settings.max_voice_seconds:
        await message.answer(
            f"Голосовое сообщение длиннее {settings.max_voice_seconds // 60} минут."
        )
        return

    submission = await get_or_create_collecting(session, db_user)
    submission.voice_file_id = message.voice.file_id
    submission.voice_duration = duration
    submission.transcript = ""
    await audit(
        session,
        db_user.telegram_id,
        submission.id,
        "voice_added",
        {"duration": duration},
    )
    await message.answer(
        "Голосовое сообщение добавлено. Можно прислать фотографии.",
        reply_markup=collecting_keyboard(submission.id),
    )


@router.callback_query(F.data.startswith("gen:") | F.data.startswith("regen:"))
async def generate_callback(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    settings: Settings,
    services: Services,
) -> None:
    await callback.answer("Формирую новость…")
    _, submission_id = callback.data.split(":", 1)
    submission = await _get_allowed_submission(session, db_user, submission_id)
    if not submission:
        await callback.message.answer("Материал не найден или у вас нет доступа.")
        return
    allowed = {
        SubmissionStatus.COLLECTING.value,
        SubmissionStatus.PREVIEW.value,
        SubmissionStatus.REJECTED.value,
        SubmissionStatus.FAILED.value,
        SubmissionStatus.AWAITING_EDITOR.value,
    }
    if submission.status not in allowed:
        await callback.message.answer("Материал уже обрабатывается или завершён.")
        return
    if not submission.raw_text.strip() and not submission.voice_file_id:
        await callback.message.answer("Сначала добавьте текст или голосовое сообщение.")
        return

    previous_status = submission.status
    submission.status = SubmissionStatus.GENERATING.value
    await audit(session, db_user.telegram_id, submission.id, "generation_started")
    await session.commit()

    review_mode = is_editor(db_user) and (
        submission.author_id != db_user.telegram_id
        or submission.author_role == UserRole.VOLUNTEER.value
        and bool(submission.wp_post_id)
    )
    try:
        article = await generate_article(
            callback.bot,
            session,
            submission,
            services,
            settings,
            revision_note=submission.rejection_comment,
        )
        needs_wordpress = review_mode or submission.author_role in {
            UserRole.ADMIN.value,
            UserRole.EDITOR.value,
        }
        if needs_wordpress:
            await sync_draft_to_wordpress(
                callback.bot,
                session,
                submission,
                article,
                services,
                settings,
            )
        submission.status = (
            SubmissionStatus.AWAITING_EDITOR.value
            if review_mode
            else SubmissionStatus.PREVIEW.value
        )
        await session.commit()
        await _send_preview(
            callback.bot,
            callback.from_user.id,
            submission,
            article,
            db_user,
            review_mode=review_mode,
        )
    except Exception as exc:
        logger.exception("Generation failed for %s", submission.id)
        submission.status = (
            previous_status
            if previous_status != SubmissionStatus.GENERATING.value
            else SubmissionStatus.FAILED.value
        )
        submission.error_message = str(exc)[:1000]
        await audit(
            session,
            db_user.telegram_id,
            submission.id,
            "generation_failed",
            {"error": type(exc).__name__},
        )
        await session.commit()
        await callback.message.answer(
            "Не удалось сформировать новость. Попробуйте ещё раз.\n"
            f"Код материала: <code>{submission.id}</code>"
        )


@router.callback_query(F.data.startswith("submit:"))
async def submit_to_editor(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    settings: Settings,
    services: Services,
) -> None:
    await callback.answer("Передаю редактору…")
    submission_id = callback.data.split(":", 1)[1]
    submission = await get_submission(session, submission_id)
    if (
        not submission
        or submission.author_id != db_user.telegram_id
        or submission.status != SubmissionStatus.PREVIEW.value
        or not submission.ai_payload
    ):
        await callback.message.answer("Материал уже передан, отменён или недоступен.")
        return
    submission.status = SubmissionStatus.SYNCING.value
    await audit(
        session,
        db_user.telegram_id,
        submission.id,
        "wordpress_sync_started",
    )
    await session.commit()
    try:
        article = Article.model_validate(submission.ai_payload)
        await sync_draft_to_wordpress(
            callback.bot,
            session,
            submission,
            article,
            services,
            settings,
        )
        submission.status = SubmissionStatus.AWAITING_EDITOR.value
        await audit(
            session,
            db_user.telegram_id,
            submission.id,
            "submitted_to_editor",
        )
        await session.commit()
        delivered = await notify_editors(
            callback.bot,
            session,
            submission,
            article,
            settings,
        )
        await session.commit()
        await callback.message.answer(
            "Новость передана редактору."
            if delivered
            else "Черновик создан, но бот не смог отправить уведомление редактору. "
            "Администратор должен открыть бота и нажать Start."
        )
    except Exception:
        logger.exception("Could not submit %s to editor", submission.id)
        submission.status = SubmissionStatus.PREVIEW.value
        await session.commit()
        await callback.message.answer("Не удалось создать черновик WordPress. Попробуйте ещё раз.")


@router.callback_query(F.data.startswith("revise:"))
async def revise_submission(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
) -> None:
    await callback.answer()
    submission_id = callback.data.split(":", 1)[1]
    submission = await get_submission(session, submission_id)
    if (
        not submission
        or submission.author_id != db_user.telegram_id
        or submission.status != SubmissionStatus.REJECTED.value
    ):
        await callback.message.answer("Материал недоступен для доработки.")
        return
    submission.status = SubmissionStatus.COLLECTING.value
    await audit(session, db_user.telegram_id, submission.id, "revision_started")
    await callback.message.answer(
        "Добавьте уточнения текстом, голосом или фотографиями. "
        "Затем снова нажмите «Сформировать новость».",
        reply_markup=collecting_keyboard(submission.id),
    )


@router.callback_query(F.data.startswith("cover:"))
async def request_cover(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
) -> None:
    await callback.answer()
    if not is_editor(db_user):
        return
    submission_id = callback.data.split(":", 1)[1]
    submission = await get_submission(session, submission_id)
    if not submission or not submission.wp_post_id:
        await callback.message.answer("Черновик не найден.")
        return
    await set_user_state(
        session,
        db_user,
        UserState.AWAITING_COVER,
        {"submission_id": submission.id},
    )
    await callback.message.answer("Пришлите одну фотографию для новой обложки.")


@router.callback_query(F.data.startswith("cancel:"))
async def cancel_submission(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    services: Services,
) -> None:
    await callback.answer()
    submission_id = callback.data.split(":", 1)[1]
    submission = await _get_allowed_submission(session, db_user, submission_id)
    if not submission:
        return
    if submission.status == SubmissionStatus.PUBLISHED.value:
        await callback.message.answer("Опубликованную новость нельзя отменить этой кнопкой.")
        return
    if submission.wp_post_id:
        try:
            await services.wordpress.cancel(submission.wp_post_id)
        except Exception:
            logger.exception("Could not trash WordPress draft %s", submission.wp_post_id)
            await callback.message.answer("Не удалось удалить черновик WordPress.")
            return
    submission.status = SubmissionStatus.CANCELLED.value
    await audit(session, db_user.telegram_id, submission.id, "submission_cancelled")
    await callback.message.answer("Материал отменён. Новый: /new")


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer("Отменено")
