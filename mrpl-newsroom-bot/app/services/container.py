from dataclasses import dataclass

from app.services.deepseek import DeepSeekEditor
from app.services.speechkit import SpeechKitTranscriber
from app.services.wordpress import WordPressClient


@dataclass(slots=True)
class Services:
    deepseek: DeepSeekEditor
    speechkit: SpeechKitTranscriber
    wordpress: WordPressClient

    async def close(self) -> None:
        await self.deepseek.close()
        await self.speechkit.close()
        await self.wordpress.close()

