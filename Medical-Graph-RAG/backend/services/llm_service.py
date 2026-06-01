from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

from ..config import Settings


class LlmService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = OpenAI(
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
        )

    def health_check(self) -> bool:
        try:
            _ = self._client.models.list()
            return True
        except Exception:
            return False

    def generate_suggestions(
        self,
        patient_info: str,
        keywords: str,
        context: str,
    ) -> list[dict[str, Any]]:
        system_prompt = (
            "You are a medical assistant. Return only strict JSON with the schema: "
            "{\"diagnosis_suggestions\": "
            "[{\"diagnosis\": string, \"confidence\": string, \"evidence\": string}]} "
            "The list must contain 3-5 items. Do not include markdown or extra keys."
        )

        user_prompt = (
            "Patient description: "
            f"{patient_info}\n"
            "Keywords: "
            f"{keywords}\n"
            "Graph context:\n"
            f"{context}\n"
            "Only use the provided context and patient info."
        )

        response = self._client.chat.completions.create(
            model=self._settings.qwen_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=600,
        )

        content = response.choices[0].message.content or ""
        payload = self._extract_json(content)
        suggestions = payload.get("diagnosis_suggestions", [])
        return [s for s in suggestions if isinstance(s, dict)]

    def _extract_json(self, text: str) -> dict[str, Any]:
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                return {}
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return {}
