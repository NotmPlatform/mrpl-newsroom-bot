from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.enums import UserRole
from app.models import User
from app.repository import audit, is_admin, list_team, revoke_role, set_role
from app.services.container import Services
from app.utils import escape

router = Router(name="admin")


@router.message(Command("role"))
async def role_command(
    message: Message,
    session: AsyncSession,
    db_user: User,
) -> None:
    if not is_admin(db_user):
        await message.answer("Команда доступна только администратору.")
        return
    parts = (message.text or "").split()
    if len(parts) != 3 or parts[2] not in {
        UserRole.EDITOR.value,
        UserRole.VOLUNTEER.value,
    }:
        await message.answer("Формат: <code>/role TELEGRAM_ID editor</code>")
        return
    try:
        telegram_id = int(parts[1])
    except ValueError:
        await message.answer("Telegram ID должен быть числом.")
        return
    if telegram_id <= 0:
        await message.answer("Некорректный Telegram ID.")
        return
    role = UserRole(parts[2])
    target = await set_role(session, telegram_id, role)
    await audit(
        session,
        db_user.telegram_id,
        None,
        "role_granted",
        {"target_id": telegram_id, "role": role.value},
    )
    await message.answer(
        f"Готово: <code>{target.telegram_id}</code> → <b>{escape(role.value)}</b>.\n"
        "Пользователь должен открыть бота и нажать Start."
    )


@router.message(Command("revoke"))
async def revoke_command(
    message: Message,
    session: AsyncSession,
    db_user: User,
    settings: Settings,
) -> None:
    if not is_admin(db_user):
        await message.answer("Команда доступна только администратору.")
        return
    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("Формат: <code>/revoke TELEGRAM_ID</code>")
        return
    try:
        telegram_id = int(parts[1])
    except ValueError:
        await message.answer("Telegram ID должен быть числом.")
        return
    if telegram_id == settings.admin_telegram_id:
        await message.answer("Нельзя отозвать роль основного администратора.")
        return
    target = await revoke_role(session, telegram_id)
    if not target:
        await message.answer("Пользователь не найден.")
        return
    await audit(
        session,
        db_user.telegram_id,
        None,
        "role_revoked",
        {"target_id": telegram_id},
    )
    await message.answer(f"Доступ пользователя <code>{telegram_id}</code> отозван.")


@router.message(Command("team"))
async def team_command(
    message: Message,
    session: AsyncSession,
    db_user: User,
) -> None:
    if not is_admin(db_user):
        return
    users = await list_team(session)
    lines = ["<b>Команда MRPL Newsroom</b>"]
    for user in users:
        name = user.full_name or user.username or "без имени"
        lines.append(
            f"\n• <code>{user.telegram_id}</code> — {escape(user.role)}"
            f"\n  {escape(name)} · {'активен' if user.active else 'отключён'}"
        )
    await message.answer("\n".join(lines))


@router.message(Command("status"))
async def status_command(
    message: Message,
    db_user: User,
    settings: Settings,
    services: Services,
) -> None:
    if not is_admin(db_user):
        return
    try:
        wp = await services.wordpress.health()
        wp_status = f"OK, WordPress {escape(wp.get('wordpress'))}"
    except Exception as exc:
        wp_status = f"ошибка: {escape(str(exc)[:300])}"
    await message.answer(
        "<b>MRPL Newsroom</b>\n"
        f"WordPress: {wp_status}\n"
        f"DeepSeek: {escape(settings.deepseek_model)}\n"
        f"SpeechKit: {'настроен' if settings.speechkit_enabled else 'не настроен'}\n"
        f"Публикация: {'включена' if settings.publish_enabled else 'тестовый режим'}"
    )

