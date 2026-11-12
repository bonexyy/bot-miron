import openai
from loguru import logger
from typing import List, Dict, Optional

logger.add(
    sink="logs/llm-client.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="DEBUG",
    rotation="1 MB",
    retention="10 days",
    compression="zip"
)


class YandexGPTClient:
    def __init__(
        self,
        api_key: str,
        folder_id: str,
        model: str = "yandexgpt-lite/latest",
        base_url: str = "https://llm.api.cloud.yandex.net/v1",
    ):
        logger.info(
            f"Initializing YandexGPTClient with model: {model}, "
            f"folder_id: {folder_id[:8]}..."
        )
        self._api_key = api_key
        self._base_url = base_url
        self.folder_id = folder_id
        self.model = model
        self.model_uri = f"gpt://{folder_id}/{model}"

        self.client = openai.OpenAI(api_key=api_key, base_url=base_url)
        self._async_client: Optional[openai.AsyncOpenAI] = None
        logger.success("YandexGPTClient initialized successfully")

    # ---------- helpers ----------

    @staticmethod
    def _build_response_format(json_mode: bool, json_schema: Optional[Dict]):
        if json_schema:
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "strict": True,
                    "schema": json_schema,
                },
            }
        if json_mode:
            return {"type": "json_object"}
        return None

    @property
    def async_client(self) -> openai.AsyncOpenAI:
        # Ленивая инициализация — создаём один раз и переиспользуем.
        if self._async_client is None:
            self._async_client = openai.AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
            )
        return self._async_client

    # ---------- sync ----------

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        json_mode: bool = False,
        json_schema: Optional[Dict] = None,
        max_tokens: int = 4000,
    ) -> str:
        response_format = self._build_response_format(json_mode, json_schema)
        try:
            logger.debug(
                f"Sync LLM call - Model: {self.model}, "
                f"Temperature: {temperature}, JSON: {json_mode}, "
                f"max_tokens: {max_tokens}"
            )
            response = self.client.chat.completions.create(
                model=self.model_uri,
                messages=messages,
                temperature=0.6 if temperature is None else temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )
            content = response.choices[0].message.content
            result = content.strip() if content else ""
            logger.info(
                f"MODEL: {self.model} | TEMP: {temperature} | "
                f"JSON: {json_mode} | LEN: {len(result)}"
            )
            return result
        except Exception as e:
            logger.error(f"YandexGPT API error: {e}")
            raise

    # ---------- async ----------

    async def chat_completion_async(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        json_mode: bool = False,
        json_schema: Optional[Dict] = None,
        max_tokens: int = 4000,
    ) -> str:
        response_format = self._build_response_format(json_mode, json_schema)
        try:
            logger.debug(
                f"Async LLM call - Model: {self.model}, "
                f"Messages: {len(messages)}, "
                f"Temperature: {temperature}, JSON: {json_mode}, "
                f"max_tokens: {max_tokens}"
            )
            response = await self.async_client.chat.completions.create(
                model=self.model_uri,
                messages=messages,
                temperature=0.6 if temperature is None else temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )
            content = response.choices[0].message.content
            result = content.strip() if content else ""
            logger.info(
                f"MODEL: {self.model} | TEMP: {temperature} | "
                f"JSON: {json_mode} | LEN: {len(result)}"
            )
            return result
        except Exception as e:
            logger.error(f"YandexGPT async API error: {e}")
            raise

    async def close(self):
        if self._async_client is not None:
            await self._async_client.close()
            self._async_client = None