from __future__ import annotations

import asyncio
import json
import re
from typing import Any, AsyncIterator

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import Settings


class LlmService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
        )

    async def health_check(self) -> bool:
        try:
            await asyncio.wait_for(self._client.models.list(), timeout=10.0)
            return True
        except Exception:
            return False

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def _call_llm(self, messages: list[dict], **kwargs) -> str:
        response = await asyncio.wait_for(
            self._client.chat.completions.create(
                model=self._settings.qwen_model,
                messages=messages,
                **kwargs,
            ),
            timeout=30.0,
        )
        return response.choices[0].message.content or ""

    async def generate_suggestions(
        self,
        patient_info: str,
        keywords: str,
        context: str,
    ) -> list[dict[str, Any]]:
        system_prompt = (
            "你是一位临床医学助手。请严格返回如下JSON格式，不要包含markdown或其他额外内容："
            '{"diagnosis_suggestions": '
            '[{"diagnosis": "诊断名称", "confidence": "高/中/低", "evidence": "基于图谱节点的推理依据"}]} '
            "诊断列表需包含3-5项。所有文本必须使用中文，包括诊断名、置信度和证据描述。"
        )

        user_prompt = (
            f"患者信息：{patient_info}\n"
            f"关键词：{keywords}\n"
            f"知识图谱上下文：\n{context}\n"
            "请仅根据提供的图谱上下文和患者信息进行推理，所有输出使用中文。"
        )

        try:
            content = await self._call_llm(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=600,
            )
        except Exception:
            return []

        payload = self._extract_json(content)
        suggestions = payload.get("diagnosis_suggestions", [])
        return [s for s in suggestions if isinstance(s, dict)]

    async def generate_suggestions_stream(
        self,
        patient_info: str,
        keywords: str,
        context: str,
    ) -> AsyncIterator[str]:
        system_prompt = (
            "你是一位临床医学助手。请严格返回如下JSON格式，不要包含markdown或其他额外内容："
            '{"diagnosis_suggestions": '
            '[{"diagnosis": "诊断名称", "confidence": "高/中/低", "evidence": "基于图谱节点的推理依据"}]} '
            "诊断列表需包含3-5项。所有文本必须使用中文。"
        )

        user_prompt = (
            f"患者信息：{patient_info}\n"
            f"关键词：{keywords}\n"
            f"知识图谱上下文：\n{context}\n"
            "请仅根据提供的图谱上下文和患者信息进行推理，所有输出使用中文。"
        )

        try:
            response = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self._settings.qwen_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.2,
                    max_tokens=600,
                    stream=True,
                ),
                timeout=30.0,
            )
            async for chunk in response:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    yield delta
        except Exception:
            yield ""

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
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
