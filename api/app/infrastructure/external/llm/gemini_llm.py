import base64
import json
import logging
import mimetypes
import uuid
from typing import Any, Dict, List, Optional

import httpx

from app.application.errors.exceptions import ServerRequestsError
from app.domain.external.llm import LLM
from app.domain.models.app_config import LLMProviderConfig

logger = logging.getLogger(__name__)


class GeminiLLM(LLM):
    """Gemini3供应商适配器，对外保持OpenAI风格消息结构"""

    def __init__(self, llm_config: LLMProviderConfig, **kwargs) -> None:
        self._base_url = str(llm_config.base_url)
        self._api_key = llm_config.api_key
        self._model_name = llm_config.model_name
        self._temperature = llm_config.temperature
        self._max_tokens = llm_config.max_tokens
        self._timeout = 3600
        self._client = httpx.AsyncClient(timeout=self._timeout, **kwargs)

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def temperature(self) -> float:
        return self._temperature

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    async def invoke(
            self,
            messages: List[Dict[str, Any]],
            tools: List[Dict[str, Any]] = None,
            response_format: Dict[str, Any] = None,
            tool_choice: str = None,
    ) -> Dict[str, Any]:
        payload = await self._build_payload(
            messages=messages,
            tools=tools or [],
            response_format=response_format,
            tool_choice=tool_choice,
        )
        headers = self._build_headers()

        try:
            logger.info("调用Gemini3供应商: %s", self._model_name)
            response = await self._client.post(self._base_url, headers=headers, json=payload)
            response.raise_for_status()
            return self._convert_response(response.json())
        except Exception as e:
            logger.error("调用Gemini3供应商发生错误: %s", e)
            raise ServerRequestsError("调用Gemini3供应商向LLM发起请求出错")

    def _build_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
            headers["x-api-key"] = self._api_key
            headers["x-goog-api-key"] = self._api_key
        return headers

    async def _build_payload(
            self,
            messages: List[Dict[str, Any]],
            tools: List[Dict[str, Any]],
            response_format: Optional[Dict[str, Any]],
            tool_choice: Optional[str],
    ) -> Dict[str, Any]:
        system_instruction = None
        contents: List[Dict[str, Any]] = []

        for message in messages:
            role = message.get("role")
            if role == "system":
                system_instruction = {
                    "parts": [{"text": self._coerce_text(message.get("content"))}],
                }
                continue

            converted = await self._convert_message(message)
            if converted:
                contents.append(converted)

        payload: Dict[str, Any] = {
            "model": self._model_name,
            "contents": contents,
            "generationConfig": {
                "temperature": self._temperature,
                "maxOutputTokens": self._max_tokens,
            },
        }
        if system_instruction:
            payload["systemInstruction"] = system_instruction
        if response_format and response_format.get("type") == "json_object":
            payload["generationConfig"]["responseMimeType"] = "application/json"
        if tools:
            payload["tools"] = [{
                "functionDeclarations": [
                    self._convert_tool_definition(tool)
                    for tool in tools
                    if tool.get("type") == "function" and tool.get("function")
                ]
            }]
            payload["toolConfig"] = {
                "functionCallingConfig": {
                    "mode": "ANY" if tool_choice == "required" else "AUTO",
                }
            }
        return payload

    async def _convert_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        role = message.get("role")
        if role == "user":
            return {
                "role": "user",
                "parts": await self._convert_content_parts(message.get("content")),
            }
        if role == "assistant":
            parts = await self._convert_content_parts(message.get("content"))
            for tool_call in message.get("tool_calls", []) or []:
                function = tool_call.get("function") or {}
                try:
                    args = json.loads(function.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {"raw_arguments": function.get("arguments") or ""}
                parts.append({
                    "functionCall": {
                        "name": function.get("name", ""),
                        "args": args,
                    }
                })
            return {
                "role": "model",
                "parts": parts or [{"text": ""}],
            }
        if role == "tool":
            response_payload = self._safe_json_loads(message.get("content"))
            return {
                "role": "user",
                "parts": [{
                    "functionResponse": {
                        "name": message.get("function_name", ""),
                        "response": response_payload,
                    }
                }],
            }
        return None

    async def _convert_content_parts(self, content: Any) -> List[Dict[str, Any]]:
        if content is None:
            return []
        if isinstance(content, str):
            return [{"text": content}]
        if not isinstance(content, list):
            return [{"text": self._coerce_text(content)}]

        parts: List[Dict[str, Any]] = []
        for item in content:
            item_type = item.get("type")
            if item_type == "text":
                parts.append({"text": item.get("text", "")})
                continue
            if item_type == "image_url":
                image_payload = await self._convert_image_part(item.get("image_url"))
                if image_payload:
                    parts.append(image_payload)
                continue
            parts.append({"text": self._coerce_text(item)})
        return parts

    async def _convert_image_part(self, image_url: Any) -> Optional[Dict[str, Any]]:
        if isinstance(image_url, dict):
            url = image_url.get("url", "")
        else:
            url = str(image_url or "")
        if not url:
            return None
        if url.startswith("data:"):
            mime_type, encoded = self._split_data_url(url)
            return {"inlineData": {"mimeType": mime_type, "data": encoded}}

        response = await self._client.get(url)
        response.raise_for_status()
        mime_type = response.headers.get("content-type") or mimetypes.guess_type(url)[0] or "image/png"
        return {
            "inlineData": {
                "mimeType": mime_type,
                "data": base64.b64encode(response.content).decode("ascii"),
            }
        }

    @staticmethod
    def _split_data_url(data_url: str) -> tuple[str, str]:
        header, encoded = data_url.split(",", 1)
        mime_type = "image/png"
        if ";" in header and ":" in header:
            mime_type = header.split(":", 1)[1].split(";", 1)[0] or mime_type
        return mime_type, encoded

    @staticmethod
    def _convert_tool_definition(tool: Dict[str, Any]) -> Dict[str, Any]:
        function = tool.get("function") or {}
        return {
            "name": function.get("name", ""),
            "description": function.get("description", ""),
            "parameters": function.get("parameters", {"type": "object", "properties": {}}),
        }

    @staticmethod
    def _safe_json_loads(content: Any) -> Dict[str, Any]:
        if isinstance(content, dict):
            return content
        if isinstance(content, str):
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {"content": content}
        return {"content": content}

    @staticmethod
    def _coerce_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False)

    @staticmethod
    def _convert_response(payload: Dict[str, Any]) -> Dict[str, Any]:
        candidates = payload.get("candidates") or []
        if not candidates:
            raise ServerRequestsError("Gemini3供应商返回空响应")

        candidate = candidates[0]
        parts = ((candidate.get("content") or {}).get("parts")) or []
        content_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []

        for part in parts:
            if "text" in part:
                content_parts.append(part.get("text", ""))
                continue
            function_call = part.get("functionCall")
            if function_call:
                tool_calls.append({
                    "id": str(uuid.uuid4()),
                    "type": "function",
                    "function": {
                        "name": function_call.get("name", ""),
                        "arguments": json.dumps(function_call.get("args", {}), ensure_ascii=False),
                    },
                })

        return {
            "role": "assistant",
            "content": "".join(content_parts) if content_parts else None,
            "tool_calls": tool_calls or None,
        }
