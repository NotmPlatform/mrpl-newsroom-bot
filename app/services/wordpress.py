from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import Settings
from app.schemas import Article
from app.services.media import PreparedImage


class WordPressError(RuntimeError):
    pass


class WordPressClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = httpx.AsyncClient(
            base_url=settings.wp_url,
            auth=httpx.BasicAuth(
                settings.wp_username,
                settings.wp_application_password.replace(" ", ""),
            ),
            timeout=httpx.Timeout(60.0, connect=20.0),
            follow_redirects=True,
            headers={"User-Agent": "MRPL-Newsroom/1.0"},
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def health(self) -> dict[str, Any]:
        return await self._json_request("GET", "/wp-json/mrpl-news/v1/health")

    async def upload_image(self, image: PreparedImage, alt_text: str) -> int:
        response = await self.client.post(
            "/wp-json/wp/v2/media",
            headers={
                "Content-Disposition": f'attachment; filename="{image.filename}"',
                "Content-Type": image.content_type,
            },
            content=image.content,
        )
        if response.status_code >= 400:
            raise WordPressError(
                f"WordPress media HTTP {response.status_code}: {response.text[:700]}"
            )
        payload = response.json()
        media_id = int(payload["id"])
        await self._json_request(
            "POST",
            f"/wp-json/wp/v2/media/{media_id}",
            json={"alt_text": alt_text},
        )
        return media_id

    async def create_or_update_draft(
        self,
        submission_id: str,
        telegram_author_id: int,
        article: Article,
        media_ids: list[int],
    ) -> dict[str, Any]:
        return await self._json_request(
            "POST",
            "/wp-json/mrpl-news/v1/drafts",
            json={
                "submission_id": submission_id,
                "telegram_author_id": str(telegram_author_id),
                "category_ids": [self.settings.wp_news_category_id],
                "media_ids": media_ids,
                "article": article.model_dump(mode="json"),
            },
        )

    async def get_post(self, post_id: int) -> dict[str, Any]:
        return await self._json_request(
            "GET",
            f"/wp-json/mrpl-news/v1/drafts/{post_id}",
        )

    async def publish(self, post_id: int, submission_id: str) -> dict[str, Any]:
        return await self._json_request(
            "POST",
            f"/wp-json/mrpl-news/v1/drafts/{post_id}/publish",
            json={"submission_id": submission_id},
        )

    async def reject(self, post_id: int, reason: str) -> dict[str, Any]:
        return await self._json_request(
            "POST",
            f"/wp-json/mrpl-news/v1/drafts/{post_id}/reject",
            json={"reason": reason},
        )

    async def cancel(self, post_id: int) -> dict[str, Any]:
        return await self._json_request(
            "POST",
            f"/wp-json/mrpl-news/v1/drafts/{post_id}/cancel",
        )

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, WordPressError)),
        wait=wait_exponential(multiplier=1, min=2, max=12),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _json_request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = await self.client.request(method, path, json=json)
        if response.status_code >= 400:
            raise WordPressError(
                f"WordPress HTTP {response.status_code}: {response.text[:700]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise WordPressError("WordPress вернул не-JSON ответ.") from exc
        if not isinstance(payload, dict):
            raise WordPressError("WordPress вернул неожиданный ответ.")
        return payload

