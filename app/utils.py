import html
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from app.schemas import Article


def new_submission_id() -> str:
    return uuid.uuid4().hex


def escape(value: object) -> str:
    return html.escape(str(value or ""), quote=False)


def clip(value: str, limit: int) -> str:
    value = value.strip()
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def article_preview(article: Article, submission_id: str) -> str:
    lines = [
        "📰 <b>Предпросмотр новости</b>",
        "",
        f"<b>{escape(article.title)}</b>",
        "",
        escape(clip(article.lead, 700)),
    ]
    if article.facts:
        lines.extend(["", "<b>Главное:</b>"])
        lines.extend(f"• {escape(clip(fact, 220))}" for fact in article.facts[:5])
    if article.uncertainties:
        lines.extend(["", "⚠️ <b>Нужно проверить:</b>"])
        lines.extend(f"• {escape(clip(item, 220))}" for item in article.uncertainties[:4])
    lines.extend(["", f"<code>{submission_id}</code>"])
    return "\n".join(lines)


def local_time(timezone_name: str) -> str:
    return datetime.now(ZoneInfo(timezone_name)).strftime("%d.%m.%Y %H:%M")

