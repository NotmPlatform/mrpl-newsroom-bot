import asyncio
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from aiogram import Bot
from PIL import Image, ImageOps

from app.config import Settings


@dataclass(slots=True)
class PreparedImage:
    content: bytes
    filename: str
    content_type: str = "image/jpeg"


async def download_telegram_file(bot: Bot, file_id: str, destination: Path) -> Path:
    file = await bot.get_file(file_id)
    if not file.file_path:
        raise RuntimeError("Telegram не вернул путь к файлу.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    await bot.download_file(file.file_path, destination=destination)
    return destination


async def prepare_telegram_image(
    bot: Bot,
    file_id: str,
    settings: Settings,
    submission_id: str,
    index: int,
) -> PreparedImage:
    file = await bot.get_file(file_id)
    if not file.file_path:
        raise RuntimeError("Telegram не вернул путь к фотографии.")
    buffer = BytesIO()
    await bot.download_file(file.file_path, destination=buffer)
    raw = buffer.getvalue()
    content = await asyncio.to_thread(_normalize_jpeg, raw, settings.max_image_side)
    return PreparedImage(
        content=content,
        filename=f"mrpl-{submission_id[:10]}-{index + 1}.jpg",
    )


def _normalize_jpeg(raw: bytes, max_side: int) -> bytes:
    with Image.open(BytesIO(raw)) as original:
        image = ImageOps.exif_transpose(original)
        if image.mode not in ("RGB", "L"):
            background = Image.new("RGB", image.size, "white")
            if "A" in image.getbands():
                background.paste(image, mask=image.getchannel("A"))
            else:
                background.paste(image)
            image = background
        elif image.mode == "L":
            image = image.convert("RGB")
        else:
            image = image.copy()

        image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        output = BytesIO()
        image.save(
            output,
            format="JPEG",
            quality=88,
            optimize=True,
            progressive=True,
        )
        return output.getvalue()

