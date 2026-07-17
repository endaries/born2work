"""
Розшифровка голосових повідомлень у текст через OpenAI Whisper API.
Anthropic не має свого STT (speech-to-text), тому для цього
використовується окремий провайдер.
"""
from openai import AsyncOpenAI


class VoiceTranscriber:
    def __init__(self, api_key: str):
        self.client = AsyncOpenAI(api_key=api_key)

    async def transcribe(self, audio_bytes: bytes, filename: str = "voice.ogg") -> str:
        # OpenAI SDK очікує файлоподібний об'єкт з .name для визначення формату
        file_tuple = (filename, audio_bytes)
        transcript = await self.client.audio.transcriptions.create(
            model="whisper-1",
            file=file_tuple,
        )
        return transcript.text.strip()