from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def collecting_keyboard(submission_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✨ Сформировать новость",
                    callback_data=f"gen:{submission_id}",
                )
            ],
            [
                InlineKeyboardButton(text="🗑 Отменить", callback_data=f"cancel:{submission_id}")
            ],
        ]
    )


def volunteer_preview_keyboard(submission_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Передать редактору",
                    callback_data=f"submit:{submission_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔁 Переписать",
                    callback_data=f"regen:{submission_id}",
                ),
                InlineKeyboardButton(
                    text="🗑 Отменить",
                    callback_data=f"cancel:{submission_id}",
                ),
            ],
        ]
    )


def editor_preview_keyboard(submission_id: str, edit_url: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="🚀 Опубликовать",
                callback_data=f"publish:{submission_id}",
            )
        ]
    ]
    if edit_url:
        rows.append([InlineKeyboardButton(text="✏️ Открыть черновик", url=edit_url)])
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="🔁 Переписать",
                    callback_data=f"regen:{submission_id}",
                ),
                InlineKeyboardButton(
                    text="🖼 Сменить обложку",
                    callback_data=f"cover:{submission_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data=f"cancel:{submission_id}",
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def editor_review_keyboard(submission_id: str, edit_url: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="✅ Опубликовать",
                callback_data=f"publish:{submission_id}",
            )
        ]
    ]
    if edit_url:
        rows.append([InlineKeyboardButton(text="✏️ Проверить черновик", url=edit_url)])
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="🔁 Переписать",
                    callback_data=f"regen:{submission_id}",
                ),
                InlineKeyboardButton(
                    text="🖼 Сменить обложку",
                    callback_data=f"cover:{submission_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отклонить с комментарием",
                    callback_data=f"reject:{submission_id}",
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def rejected_author_keyboard(submission_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔁 Доработать",
                    callback_data=f"revise:{submission_id}",
                ),
                InlineKeyboardButton(
                    text="Закрыть",
                    callback_data=f"cancel:{submission_id}",
                ),
            ]
        ]
    )


def confirm_role_keyboard(user_id: int, role: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подтвердить",
                    callback_data=f"roleok:{user_id}:{role}",
                ),
                InlineKeyboardButton(text="Отмена", callback_data="noop"),
            ]
        ]
    )


def admin_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Добавить / изменить роль",
                    callback_data="team:add",
                )
            ],
            [
                InlineKeyboardButton(
                    text="👥 Показать команду",
                    callback_data="team:list",
                ),
                InlineKeyboardButton(
                    text="🚫 Отозвать доступ",
                    callback_data="team:revoke",
                ),
            ],
        ]
    )


def admin_team_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Добавить / изменить роль",
                    callback_data="team:add",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Отозвать доступ",
                    callback_data="team:revoke",
                ),
                InlineKeyboardButton(
                    text="🔄 Обновить список",
                    callback_data="team:list",
                ),
            ],
        ]
    )


def role_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🙋 Волонтёр",
                    callback_data="team:role:volunteer",
                ),
                InlineKeyboardButton(
                    text="✍️ Редактор",
                    callback_data="team:role:editor",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data="team:cancel",
                )
            ],
        ]
    )


def confirm_revoke_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚫 Отозвать доступ",
                    callback_data=f"revokeok:{user_id}",
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data="team:cancel",
                ),
            ]
        ]
    )
