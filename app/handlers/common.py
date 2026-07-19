from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.enums import SubmissionStatus
from app.keyboards import admin_home_keyboard
from app.models import User
from app.repository import (
    create_submission,
    get_collecting_submission,
    is_authorized,
    list_user_submissions,
)
from app.utils import escape

router = Router(name="common")

STATUS_LABELS = {
    SubmissionStatus.COLLECTING.value: "собирается",
    SubmissionStatus.GENERATING.value: "формируется",
    SubmissionStatus.SYNCING.value: "создаётся черновик",
    SubmissionStatus.PREVIEW.value: "на вашей проверке",
    SubmissionStatus.AWAITING_EDITOR.value: "у редактора",
    SubmissionStatus.PUBLISHING.value: "публикуется",
    SubmissionStatus.REJECTED.value: "нужна доработка",
    SubmissionStatus.PUBLISHED.value: "опубликована",
    SubmissionStatus.CANCELLED.value: "отменена",
    SubmissionStatus.FAILED.value: "ошибка",
}


@router.message(CommandStart())
async def start(message: Message, db_user: User) -> None:
    if not is_authorized(db_user):
        await message.answer(
            "Ваш Telegram ID:\n"
            f"<code>{message.from_user.id}</code>\n\n"
            "Доступ ещё не выдан. Отправьте этот ID администратору."
        )
        return
    await message.answer(
        "MRPL Newsroom готов.\n\n"
        "Нажмите /new или сразу пришлите текст, голосовое сообщение и фотографии."
    )
    if db_user.role == "admin":
        await message.answer(
            "<b>Управление командой</b>\n"
            "Добавляйте сотрудников и меняйте их роли кнопками.",
            reply_markup=admin_home_keyboard(),
        )


@router.message(Command("myid"))
async def my_id(message: Message) -> None:
    await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>")


@router.message(Command("help"))
async def help_command(message: Message, db_user: User) -> None:
    if not is_authorized(db_user):
        await message.answer("Доступ не выдан. Узнать ID: /myid")
        return
    text = (
        "<b>Как отправить новость</b>\n"
        "1. Нажмите /new.\n"
        "2. Пришлите текст или голосовое сообщение.\n"
        "3. Добавьте до 10 фотографий.\n"
        "4. Нажмите «Сформировать новость».\n"
        "5. Проверьте результат и подтвердите.\n\n"
        "/queue — ваши последние материалы\n"
        "/cancel — отменить текущий материал\n"
        "/myid — ваш Telegram ID"
    )
    if db_user.role == "admin":
        text += (
            "\n\n<b>Администратор</b>\n"
            "/role ID editor\n"
            "/role ID volunteer\n"
            "/revoke ID\n"
            "/team\n"
            "/status"
        )
    await message.answer(text)


@router.message(Command("new"))
async def new_submission(
    message: Message,
    session: AsyncSession,
    db_user: User,
) -> None:
    if not is_authorized(db_user):
        await message.answer("Доступ не выдан. Ваш ID: /myid")
        return
    existing = await get_collecting_submission(session, db_user.telegram_id)
    submission = existing or await create_submission(session, db_user)
    await message.answer(
        "Пришлите текст или голосовое сообщение, затем фотографии.\n"
        "Когда всё будет добавлено, нажмите «Сформировать новость».\n\n"
        f"Материал: <code>{submission.id}</code>"
    )


@router.message(Command("cancel"))
async def cancel_current(
    message: Message,
    session: AsyncSession,
    db_user: User,
) -> None:
    if not is_authorized(db_user):
        return
    submission = await get_collecting_submission(session, db_user.telegram_id)
    if not submission:
        await message.answer("Сейчас нет материала, который собирается.")
        return
    submission.status = SubmissionStatus.CANCELLED.value
    await message.answer("Текущий материал отменён. Новый: /new")


@router.message(Command("queue"))
async def queue(
    message: Message,
    session: AsyncSession,
    db_user: User,
    settings: Settings,
) -> None:
    if not is_authorized(db_user):
        return
    submissions = await list_user_submissions(session, db_user.telegram_id)
    if not submissions:
        await message.answer("У вас пока нет материалов.")
        return
    lines = ["<b>Ваши последние материалы</b>"]
    for item in submissions:
        title = (item.ai_payload or {}).get("title") or item.raw_text or "Без названия"
        label = STATUS_LABELS.get(item.status, item.status)
        lines.append(
            f"\n• <b>{escape(title[:90])}</b>\n"
            f"  {escape(label)} · <code>{item.id}</code>"
        )
    await message.answer("\n".join(lines))
