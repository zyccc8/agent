from __future__ import annotations

import json
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import get_config_value


class LLMError(RuntimeError):
    pass


class CustomLLMClient:
    """Small adapter for user-owned OpenAI-compatible LLM APIs.

    Supported formats:
    - chat: POST /v1/chat/completions style, response choices[0].message.content
    - responses: POST /v1/responses style, response output_text or output[].content[].text
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        api_format: Optional[str] = None,
        timeout: int = 45,
    ) -> None:
        self.api_url = api_url or get_config_value("LLM_API_URL")
        self.api_key = api_key or get_config_value("LLM_API_KEY")
        self.model = model or get_config_value("LLM_MODEL")
        self.api_format = (api_format or get_config_value("LLM_API_FORMAT") or self._infer_format()).lower()
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.api_url)

    def complete_json(self, instructions: str, prompt: str) -> Dict[str, Any]:
        if not self.api_url:
            raise LLMError("LLM_API_URL is not configured")

        payload = self._build_payload(instructions, prompt)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(
            self.api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"LLM API error {exc.code}: {detail}") from exc
        except URLError as exc:
            raise LLMError(f"LLM API network error: {exc.reason}") from exc

        data = json.loads(raw)
        text = extract_output_text(data, self.api_format)
        if not text:
            raise LLMError("LLM API returned no output text")
        return parse_json_object(text)

    def _infer_format(self) -> str:
        if "chat/completions" in self.api_url:
            return "chat"
        return "responses"

    def _build_payload(self, instructions: str, prompt: str) -> Dict[str, Any]:
        model = self.model or "default"
        if self.api_format == "chat":
            return {
                "model": model,
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
            }
        if self.api_format == "responses":
            return {
                "model": model,
                "instructions": instructions,
                "input": prompt,
                "temperature": 0.2,
            }
        raise LLMError(f"Unsupported LLM_API_FORMAT: {self.api_format}")


def extract_output_text(response: Dict[str, Any], api_format: str = "responses") -> str:
    if api_format == "chat":
        choices = response.get("choices", [])
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message", {})
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"].strip()

    if isinstance(response.get("output_text"), str):
        return response["output_text"]

    chunks = []
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and "text" in content:
                chunks.append(content["text"])
    return "\n".join(chunks).strip()


def parse_json_object(text: str) -> Dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise LLMError("Model output is not valid JSON")
        parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, dict):
        raise LLMError("Model output JSON must be an object")
    return parsed
