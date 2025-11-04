from __future__ import annotations

import numpy as np
from sqlmodel.ext.asyncio.session import AsyncSession

from classification.inference import (
    InferenceResult,
    _load_enabled_prototypes,
    predict_document_class,
)
from classification.models import ClassPrototype, DocClass, HeaderWeight
from tests.utils import load_fixtures  # type: ignore[import]


async def test_load_enabled_prototypes_filters_disabled_and_normalizes(any_session: AsyncSession):
    load_fixtures('classification_enabled_prototypes.sql')

    result = await _load_enabled_prototypes(any_session)

    assert set(result.keys()) == {'integration_enabled_class'}
    vec = result['integration_enabled_class']
    assert isinstance(vec, np.ndarray)
    np.testing.assert_allclose(vec, np.array([0.6, 0.8], dtype=float), rtol=1e-6)
    assert np.isclose(float(np.linalg.norm(vec)), 1.0)


async def test_predict_document_class_with_header_boost(any_session: AsyncSession):
    # Seed two classes and prototypes
    c1 = DocClass(class_name='annual_report', enabled=True)
    c2 = DocClass(class_name='company_register', enabled=True)

    # orthogonal-ish centroids in 32-D
    d = 32
    mu1 = np.zeros(d)
    mu1[0] = 1.0
    mu2 = np.zeros(d)
    mu2[1] = 1.0

    any_session.add_all(
        [
            c1,
            c2,
            ClassPrototype(class_name='annual_report', centroid=mu1.tolist(), dispersion=0.0, n_docs=10),
            ClassPrototype(class_name='company_register', centroid=mu2.tolist(), dispersion=0.0, n_docs=10),
        ]
    )

    # header weights favour "annual_report" if header contains 'management report'
    any_session.add_all(
        [
            HeaderWeight(class_name='annual_report', pattern='management report', is_regex=False, weight=1.5),
            HeaderWeight(class_name='company_register', pattern='handelsregister', is_regex=False, weight=1.5),
        ]
    )
    await any_session.commit()

    # Build chunks near mu1 with small noise; include one header that triggers the boost
    rng = np.random.default_rng(42)
    chunks: list[np.ndarray] = []
    headers = []
    for i in range(12):
        base = mu1 + 0.10 * rng.normal(size=d)
        chunks.append(base.astype(float))
        headers.append('management report' if i % 5 == 0 else 'notes')

    result: InferenceResult = await predict_document_class(
        session=any_session,
        chunk_embeddings=chunks,
        chunk_headers=headers,
        m_chunk=8,
        header_weight_scale=0.05,
    )

    assert result.predicted_class in {'annual_report', 'company_register'}
    assert result.predicted_class == 'annual_report'
    assert result.prob > 0.5
    assert result.margin > 0.0
    assert result.chunks_used <= 8


async def test_predict_document_class_informative_selection(any_session: AsyncSession):
    # Seed simple 16-D centroids
    d = 16
    mu1 = np.zeros(d)
    mu1[0] = 1.0
    mu2 = np.zeros(d)
    mu2[1] = 1.0

    for obj in [
        DocClass(class_name='annual_report', enabled=True),
        DocClass(class_name='company_register', enabled=True),
        ClassPrototype(class_name='annual_report', centroid=mu1.tolist(), dispersion=0.0, n_docs=5),
        ClassPrototype(class_name='company_register', centroid=mu2.tolist(), dispersion=0.0, n_docs=5),
    ]:
        any_session.add(obj)
    await any_session.commit()

    # Create chunks: most near mu2, a few near mu1; ensure m_chunk selects the most informative ones
    rng = np.random.default_rng(7)
    chunks = []
    headers = []
    for i in range(20):
        if i < 4:
            v = mu1 + 0.25 * rng.normal(size=d)
            headers.append("auditor's report")
        else:
            v = mu2 + 0.25 * rng.normal(size=d)
            headers.append('registergericht')
        chunks.append(v.astype(float))

    res = await predict_document_class(
        session=any_session,
        chunk_embeddings=chunks,
        chunk_headers=headers,
        m_chunk=6,
        header_weight_scale=0.0,  # test pure informative selection
    )

    assert res.predicted_class == 'company_register'
    assert res.chunks_used == 6
    assert res.margin > 0
