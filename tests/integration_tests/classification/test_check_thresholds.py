# File: tests/test_api.py

from uuid import uuid4

import pytest

from classification.api import check_threshold
from classification.inference import InferenceResult
from classification.schemas import PredictByChunks, PredictByDigest, Thresholds


@pytest.mark.asyncio
async def test_check_threshold_no_thresholds():
    payload = PredictByDigest(
        mode='by_digest',
        document_id=uuid4(),
        digests=['test_digest'],
        thresholds=None,
    )
    inference = InferenceResult(predicted_class='test', prob=0.9, margin=0.5, chunks_used=5, scores={})
    result = await check_threshold(payload=payload, inference=inference)
    assert result == (False, None)


@pytest.mark.asyncio
async def test_check_threshold_below_min_prob():
    payload = PredictByChunks(
        mode='by_chunks',
        document_id=uuid4(),
        chunk_embeddings=[[0.1, 0.2], [0.2, 0.3]],
        thresholds=Thresholds(min_prob=0.8),
    )
    inference = InferenceResult(predicted_class='test', prob=0.7, margin=0.5, chunks_used=5, scores={})
    result = await check_threshold(payload=payload, inference=inference)
    assert result == (True, 'below_min_prob')


@pytest.mark.asyncio
async def test_check_threshold_below_min_margin():
    payload = PredictByDigest(
        mode='by_digest',
        document_id=uuid4(),
        digests=['test_digest'],
        thresholds=Thresholds(min_margin=0.6),
    )
    inference = InferenceResult(predicted_class='test', prob=0.9, margin=0.5, chunks_used=5, scores={})
    result = await check_threshold(payload=payload, inference=inference)
    assert result == (True, 'below_min_margin')


@pytest.mark.asyncio
async def test_check_threshold_below_min_chunks():
    payload = PredictByChunks(
        mode='by_chunks',
        document_id=uuid4(),
        chunk_embeddings=[[0.1, 0.2], [0.2, 0.3]],
        thresholds=Thresholds(min_chunks=10),
    )
    inference = InferenceResult(predicted_class='test', prob=0.9, margin=0.5, chunks_used=5, scores={})
    result = await check_threshold(payload=payload, inference=inference)
    assert result == (True, 'below_min_chunks')


@pytest.mark.asyncio
async def test_check_threshold_all_conditions_met():
    payload = PredictByChunks(
        mode='by_chunks',
        document_id=uuid4(),
        chunk_embeddings=[[0.1, 0.2], [0.2, 0.3]],
        thresholds=Thresholds(min_prob=0.8, min_margin=0.4, min_chunks=2),
    )
    inference = InferenceResult(predicted_class='test', prob=0.9, margin=0.5, chunks_used=5, scores={})
    result = await check_threshold(payload=payload, inference=inference)
    assert result == (False, None)
