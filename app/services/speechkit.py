import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import Settings


class SpeechKitError(RuntimeError):
    pass


class SpeechKitTranscriber:
    ENDPOINT = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(50.0, connect=15.0))

    async def close(self) -> None:
        await self.client.aclose()

    async def transcribe(self, source: Path) -> str:
        if not self.settings.speechkit_enabled:
            raise SpeechKitError(
                "SpeechKit не настроен: заполните YANDEX_FOLDER_ID и YANDEX_API_KEY."
            )

        with TemporaryDirectory(prefix="mrpl-stt-") as temp:
            chunks = await self._split_audio(source, Path(temp))
            texts: list[str] = []
            for chunk in chunks:
                text = await self._recognize_chunk(chunk)
                if text:
                    texts.append(text.strip())
            result = " ".join(texts).strip()
            if not result:
                raise SpeechKitError("SpeechKit не распознал речь в голосовом сообщении.")
            return result

    async def _split_audio(self, source: Path, target_dir: Path) -> list[Path]:
        pattern = target_dir / "part-%03d.ogg"
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-ac",
            "1",
            "-c:a",
            "libopus",
            "-b:a",
            "32k",
            "-f",
            "segment",
            "-segment_time",
            "28",
            "-reset_timestamps",
            "1",
            str(pattern),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            raise SpeechKitError(
                f"Не удалось подготовить голосовое сообщение: {stderr.decode(errors='ignore')[:500]}"
            )

        chunks = sorted(target_dir.glob("part-*.ogg"))
        if not chunks:
            raise SpeechKitError("После обработки голосового сообщения не осталось аудио.")
        if any(chunk.stat().st_size > 1_000_000 for chunk in chunks):
            raise SpeechKitError("Один из аудиофрагментов превышает лимит SpeechKit 1 МБ.")
        return chunks

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, SpeechKitError)),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _recognize_chunk(self, path: Path) -> str:
        response = await self.client.post(
            self.ENDPOINT,
            params={
                "topic": "general",
                "lang": "ru-RU",
                "format": "oggopus",
                "folderId": self.settings.yandex_folder_id,
            },
            headers={"Authorization": f"Api-Key {self.settings.yandex_api_key}"},
            content=path.read_bytes(),
        )
        if response.status_code >= 400:
            raise SpeechKitError(
                f"SpeechKit HTTP {response.status_code}: {response.text[:500]}"
            )
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise SpeechKitError("SpeechKit вернул некорректный ответ.") from exc
        if payload.get("error_code"):
            raise SpeechKitError(
                f"SpeechKit {payload.get('error_code')}: {payload.get('error_message', '')}"
            )
        return str(payload.get("result", ""))

