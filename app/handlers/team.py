from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.enums import UserRole, UserState
from app.keyboards import admin_team_keyboard, role_choice_keyboard
from app.models import User
from app.repository import (
    audit,
    is_admin,
    list_team,
    revoke_role,
    set_role,
    set_user_state,
)
from app.utils import escape

router = Router(name="team")

ROLE_LABELS = {
    UserRole.ADMIN.value: "администратор",
    UserRole.EDITOR.value: "редактор",
    UserRole.VOLUNTEER.value: "волонтёр",
}


async def _send_team(message: Message, session: AsyncSession) -> None:
    users = await list_team(session)
    lines = ["<b>Команда MRPL Newsroom</b>"]
    if not users:
        lines.append("\nСотрудников пока нет.")
    for user in users:
        name = user.full_name or user.username or "без имени"
        role = ROLE_LABELS.get(user.role or "", user.role or "без роли")
        status = "активен" if user.active else "отключён"
        lines.append(
            f"\n• <code>{user.telegram_id}</code> — <b>{escape(role)}</b>"
            f"\n  {escape(name)} · {status}"
        )
    await message.answer(
        "\n".join(lines),
        reply_markup=admin_team_keyboard(),
    )


@router.callback_query(F.data == "team:list")
async def team_list_callback(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
) -> None:
    await callback.answer()
    if not is_admin(db_user) or not callback.message:
        return
    await _send_team(callback.message, session)


@router.callback_query(F.data == "team:add")
async def team_add_callback(
    callback: CallbackQuery,
    db_user: User,
) -> None:
    await callback.answer()
    if not is_admin(db_user) or not callback.message:
        return
    await callback.message.answer(
        "<b>Какую роль выдать сотруднику?</b>\n\n"
        "Если этот Telegram ID уже есть в команде, его роль будет изменена.",
        reply_markup=role_choice_keyboard(),
    )


@router.callback_query(F.data.startswith("team:role:"))
async def team_role_callback(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
) -> None:
    await callback.answer()
    if not is_admin(db_user) or not callback.message:
        return
    role = callback.data.rsplit(":", 1)[-1]
    if role not in ROLE_LABELS:
        await callback.message.answer("Неизвестная роль.")
        return
    await set_user_state(
        session,
        db_user,
        UserState.AWAITING_TEAM_MEMBER_ID,
        {"action": "set_role", "role": role},
    )
    await callback.message.answer(
        f"Отправьте <b>Telegram ID</b> сотрудника.\n"
        f"Выбранная роль: <b>{ROLE_LABELS[role]}</b>.\n\n"
        "ID можно узнать у сотрудника командой /myid."
    )


@router.callback_query(F.data == "team:revoke")
async def team_revoke_callback(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
) -> None:
    await callback.answer()
    if not is_admin(db_user) or not callback.message:
        return
    await set_user_state(
        session,
        db_user,
        UserState.AWAITING_TEAM_MEMBER_ID,
        {"action": "revoke"},
    )
    await callback.message.answer(
        "Отправьте <b>Telegram ID</b> сотрудника, у которого нужно отозвать доступ."
    )


@router.callback_query(F.data == "team:cancel")
async def team_cancel_callback(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
) -> None:
    await callback.answer("Отменено")
    if not is_admin(db_user):
        return
    await set_user_state(session, db_user, UserState.IDLE)
    if callback.message:
        await callback.message.answer(
            "Действие отменено.",
            reply_markup=admin_team_keyboard(),
        )


@router.callback_query(F.data.startswith("roleok:"))
async def role_confirm_callback(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    settings: Settings,
) -> None:
    await callback.answer()
    if not is_admin(db_user) or not callback.message:
        return
    try:
        _, raw_id, role_value = callback.data.split(":", 2)
        telegram_id = int(raw_id)
        role = UserRole(role_value)
    except (TypeError, ValueError):
        await callback.message.answer("Не удалось прочитать Telegram ID или роль.")
        return
    if role not in {UserRole.EDITOR, UserRole.VOLUNTEER} or telegram_id <= 0:
        await callback.message.answer("Некорректный Telegram ID или роль.")
        return
    if telegram_id == settings.admin_telegram_id:
        await callback.message.answer("Роль основного администратора изменять нельзя.")
        return

    target = await set_role(session, telegram_id, role)
    await audit(
        session,
        db_user.telegram_id,
        None,
        "role_granted",
        {"target_id": telegram_id, "role": role.value, "source": "button"},
    )
    await callback.message.answer(
        f"Готово: <code>{target.telegram_id}</code> → "
        f"<b>{ROLE_LABELS[role.value]}</b>.\n\n"
        "Сотруднику нужно открыть бота и нажать Start.",
        reply_markup=admin_team_keyboard(),
    )


@router.callback_query(F.data.startswith("revokeok:"))
async def revoke_confirm_callback(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    settings: Settings,
) -> None:
    await callback.answer()
    if not is_admin(db_user) or not callback.message:
        return
    try:
        telegram_id = int(callback.data.split(":", 1)[1])
    except (TypeError, ValueError):
        await callback.message.answer("Не удалось прочитать Telegram ID.")
        return
    if telegram_id == settings.admin_telegram_id:
        await callback.message.answer("Доступ основного администратора отозвать нельзя.")
        return

    target = await revoke_role(session, telegram_id)
    if not target:
        await callback.message.answer(
            "Сотрудник с таким Telegram ID не найден.",
            reply_markup=admin_team_keyboard(),
        )
        return
    await audit(
        session,
        db_user.telegram_id,
        None,
        "role_revoked",
        {"target_id": telegram_id, "source": "button"},
    )
    await callback.message.answer(
        f"Доступ пользователя <code>{telegram_id}</code> отозван.",
        reply_markup=admin_team_keyboard(),
    )
