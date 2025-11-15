from __future__ import annotations

import json
from typing import Any, Callable
from uuid import uuid4

from datasifter.interfaces import MapEngine as MapEngineInterface
from datasifter.prompts import map_prompt_messages
from datasifter.schemas import (
    AttributeSpec,
    Candidate,
    RetrievalMetadata,
    RetrievedChunk,
)
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel


class MapEngine(MapEngineInterface):
    def __init__(self, *, model_name: str, llm: BaseChatModel | None = None):
        self._model_name = model_name
        self._llm = llm or init_chat_model(model=model_name, temperature=0)

    @staticmethod
    def _parse_json(content: str | None) -> dict[str, Any] | None:
        if not content:
            return None
        text = content.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            try:
                start = text.index('{')
                end = text.rindex('}') + 1
                return json.loads(text[start:end])
            except (ValueError, json.JSONDecodeError):
                return None

    async def extract_candidate(
        self,
        *,
        doc_type: str,
        attribute: AttributeSpec,
        chunk: RetrievedChunk,
        attempt: int,
        prompt_id: str | None = None,
    ) -> Candidate:
        prompt_tag = prompt_id or f'p-{uuid4().hex[:8]}'
        messages = map_prompt_messages(
            doc_type=doc_type,
            attribute=attribute,
            chunk=chunk,
            prompt_id=prompt_tag,
            attempt=attempt,
        )
        response = await self._llm.ainvoke(messages)

        raw_content = getattr(response, 'content', None)
        payload: dict[str, Any] | None = None
        if isinstance(raw_content, str):
            payload = self._parse_json(raw_content)
        elif isinstance(raw_content, list):
            text_blocks = ''.join(block.get('text', '') for block in raw_content if isinstance(block, dict))
            payload = self._parse_json(text_blocks)

        if payload is None and hasattr(response, 'message'):
            message = getattr(response, 'message')
            if isinstance(message, dict):
                arguments = message.get('content')
                if isinstance(arguments, str):
                    payload = self._parse_json(arguments)

        if payload is None:
            payload = {'value': None, 'confidence': 0.0, 'rationale': 'LLM response missing JSON payload'}

        value = payload.get('value')
        confidence = payload.get('confidence')
        rationale = payload.get('rationale')

        if isinstance(confidence, str):
            try:
                confidence = float(confidence)
            except ValueError:
                confidence = None
        if isinstance(confidence, (int, float)):
            confidence = max(0.0, min(float(confidence), 1.0))
        else:
            confidence = None

        retrieval = RetrievalMetadata(
            chunk_id=chunk.chunk_id,
            header=chunk.header,
            page=chunk.page,
            retr_score=chunk.retr_score,
            text_excerpt=chunk.text[:320],
        )

        return Candidate(
            attribute=attribute.name,
            value=value,
            confidence_local=confidence,
            rationale=str(rationale) if rationale is not None else None,
            retrieval=retrieval,
            raw_json=payload,
        )


def build_map_engine_factory() -> Callable[[str], MapEngine]:
    def _factory(model_name: str) -> MapEngine:
        return MapEngine(model_name=model_name)

    return _factory
