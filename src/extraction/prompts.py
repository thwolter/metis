from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from .schemas import AttributeConstraints, AttributeSpec, RetrievedChunk


def _constraints_text(constraints: AttributeConstraints | None) -> str:
    if constraints is None:
        return ''
    fragments: list[str] = []
    if constraints.enum_values:
        fragments.append(f'Allowed values: {", ".join(constraints.enum_values)}.')
    if constraints.pattern:
        fragments.append(f'Pattern: {constraints.pattern}.')
    if constraints.min_value is not None:
        fragments.append(f'Minimum: {constraints.min_value}.')
    if constraints.max_value is not None:
        fragments.append(f'Maximum: {constraints.max_value}.')
    if constraints.normaliser:
        fragments.append(f'Normalise using: {constraints.normaliser}.')
    return ' '.join(fragments)


def map_prompt_messages(
    *,
    doc_type: str,
    attribute: AttributeSpec,
    chunk: RetrievedChunk,
    prompt_id: str,
    attempt: int,
) -> list[SystemMessage | HumanMessage]:
    hints_text = ''
    if attribute.hints:
        hints_text = 'Hints: ' + ', '.join(attribute.hints) + '.'
    constraints_text = _constraints_text(attribute.constraints)

    system = SystemMessage(
        content=(
            'You extract structured attributes from documents. '
            f'Target document type: {doc_type}. '
            f'Attribute: {attribute.name} ({attribute.type.value}). '
            f'Description: {attribute.description}. '
            f'{hints_text} {constraints_text} '
            'Respond in strict JSON with keys: value, confidence, rationale. '
            'Use null for value when information is not present in the chunk. '
            'Return confidence between 0 and 1. '
            'You must not hallucinate values or rely on previous chunks. '
            f'Prompt ID: {prompt_id}. Attempt: {attempt}.'
        )
    )
    metadata_lines: list[str] = []
    if chunk.header:
        metadata_lines.append(f'Header: {chunk.header}')
    if chunk.page is not None:
        metadata_lines.append(f'Page: {chunk.page}')
    if chunk.retr_score is not None:
        metadata_lines.append(f'Retrieval score: {chunk.retr_score:.4f}')
    metadata_block = '\n'.join(metadata_lines)
    human_content = (
        'Chunk metadata:\n'
        f'{metadata_block or "n/a"}\n'
        'Chunk text:\n'
        f'"""\n{chunk.text}\n"""\n'
        'JSON schema:\n'
        '{"value": <value|null>, "confidence": <float>, "rationale": <string|null>}'
    )
    human = HumanMessage(content=human_content)
    return [system, human]
