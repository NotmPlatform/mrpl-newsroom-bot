import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from pydantic import ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import Settings
from app.schemas import Article


SYSTEM_PROMPT = """
Ты — выпускающий редактор городского портала MRPL.RU.
Создай самостоятельную новость на русском языке только из фактов пользователя.

Редакционные правила:
1. Не выдумывай имена, даты, адреса, цифры, причины, цитаты, отзывы и последствия.
2. Не выдавай предположения за факты. Недостающие важные сведения занеси в uncertainties.
3. Исправляй устную речь, повторы и ошибки, но не меняй смысл.
4. Заголовок — конкретный, живой, без кликбейта, канцелярита и точки в конце.
5. В первом абзаце ответь: что произошло, где и почему это важно жителям.
6. Тон — спокойный, человечный, нейтральный. Не добавляй политическую агитацию.
7. Для обвинений, происшествий и спорных утверждений обязательно сохраняй атрибуцию:
   кто именно это сообщил. Если источника нет, пометь это в uncertainties.
8. SEO используй естественно: «Мариуполь», «новости Мариуполя» и конкретную тему,
   но не повторяй ключи механически.
9. Не добавляй HTML или Markdown.
10. Ответ верни строго как JSON-объект указанной структуры.

JSON:
{
  "title": "заголовок",
  "slug": "короткий slug латиницей",
  "lead": "лид",
  "sections": [
    {"heading": "подзаголовок", "paragraphs": ["абзац", "абзац"]}
  ],
  "facts": ["факт"],
  "quote": null,
  "source_note": "нейтральная подпись источника, если источник указан",
  "excerpt": "краткий отрывок записи",
  "seo_title": "SEO-заголовок",
  "seo_description": "описание 120–180 символов",
  "focus_keyword": "естественная ключевая фраза",
  "tags": ["Мариуполь"],
  "image_alt": "точное описание темы фотографии без выдумывания деталей кадра",
  "uncertainties": ["что редактору нужно проверить"],
  "editor_notes": ["краткая внутренняя подсказка редактору"]
}
""".strip()


class DeepSeekError(RuntimeError):
    pass


class DeepSeekEditor:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = httpx.AsyncClient(
            base_url=settings.deepseek_base_url,
            timeout=httpx.Timeout(90.0, connect=20.0),
            headers={
                "Authorization": f"Bearer {settings.deepseek_api_key}",
                "Content-Type": "application/json",
            },
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def generate(
        self,
        raw_text: str,
        transcript: str = "",
        previous_article: dict | None = None,
        revision_note: str = "",
    ) -> Article:
        now = datetime.now(ZoneInfo(self.settings.timezone)).strftime("%d.%m.%Y %H:%M")
        user_parts = [
            f"Текущее местное время: {now}.",
            "Исходный текст автора:",
            raw_text.strip() or "(текст не передан)",
        ]
        if transcript.strip():
            user_parts.extend(["", "Расшифровка голосового сообщения:", transcript.strip()])
        if previous_article:
            user_parts.extend(
                [
                    "",
                    "Предыдущая версия JSON, которую нужно улучшить:",
                    json.dumps(previous_article, ensure_ascii=False),
                ]
            )
        if revision_note.strip():
            user_parts.extend(["", "Комментарий к переработке:", revision_note.strip()])

        source = "\n".join(user_parts)
        invalid_payload: str | None = None
        validation_error: str | None = None

        for attempt in range(2):
            prompt = source
            if invalid_payload is not None:
                prompt += (
                    "\n\nПредыдущий JSON не прошёл проверку. Исправь его и верни полный JSON заново."
                    f"\nОшибка: {validation_error}\nПредыдущий ответ: {invalid_payload}"
                )
            raw_json = await self._request(prompt)
            try:
                parsed = json.loads(raw_json)
                return Article.model_validate(parsed)
            except (json.JSONDecodeError, ValidationError, TypeError) as exc:
                invalid_payload = raw_json[:12000]
                validation_error = str(exc)[:1200]
                if attempt == 1:
                    raise DeepSeekError(
                        "DeepSeek вернул некорректную структуру новости после повторной попытки."
                    ) from exc

        raise DeepSeekError("Не удалось сформировать новость.")

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, DeepSeekError)),
        wait=wait_exponential(multiplier=1, min=2, max=12),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _request(self, user_prompt: str) -> str:
        response = await self.client.post(
            "/chat/completions",
            json={
                "model": self.settings.deepseek_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
                "thinking": {"type": "disabled"},
                "temperature": 0.35,
                "max_tokens": 5000,
            },
        )
        if response.status_code >= 400:
            raise DeepSeekError(
                f"DeepSeek HTTP {response.status_code}: {response.text[:500]}"
            )
        payload = response.json()
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise DeepSeekError("DeepSeek вернул неожиданный ответ.") from exc
        if not content or not content.strip():
            raise DeepSeekError("DeepSeek вернул пустой ответ.")
        return content.strip()

