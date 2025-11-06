import pytest

from classification.inference import predict_document_class
from classification.service import (
    _fetch_doc_vectors_by_digests,
    recompute_class_prototype_batch,
)
from tests.utils import load_fixtures  # type: ignore[import]


@pytest.fixture(scope='module', autouse=True)
def load_classification_data():
    load_fixtures('vectra_roles.sql')
    load_fixtures('vectra_fixtures.sql')
    load_fixtures('vectra_classifier.sql')
    load_fixtures('classification.sql')


@pytest.mark.integration
async def test_recompute_and_update_prototypes(any_session):
    digests = ['vI7EHYpQg6bnz2PsLviZVeneXbMs9iqDQyOgUjIhClc=']  # seeded in your vector tests

    # batch
    proto = await recompute_class_prototype_batch(
        session=any_session,
        class_name='annual_report',
        digests=digests,
    )
    assert proto and proto.n_docs >= 1 and len(proto.centroid) > 10

    # online update with a third doc
    # updated = await update_class_prototype_online(
    #     session=any_session,
    #     class_name='annual_report',
    #    digest='digest_c',
    # )
    # todo: skip, until we have more documents
    # assert updated and updated.n_docs == proto.n_docs + 1


@pytest.mark.integration
async def test_predict_same_digest_matches_class(any_session):
    """Using the same digest used to train the prototype should classify back to that class."""
    digest = 'vI7EHYpQg6bnz2PsLviZVeneXbMs9iqDQyOgUjIhClc='
    class_name = 'annual_report'

    # 1) Ensure prototype exists from this digest (batch recompute on single digest)
    proto = await recompute_class_prototype_batch(
        session=any_session,
        class_name=class_name,
        digests=[digest],
    )
    assert proto is not None and proto.n_docs >= 1

    # 2) Fetch the same chunk vectors from vectra (no collection filter, by digest)
    vecs_by_digest = await _fetch_doc_vectors_by_digests(
        digests=[digest],
    )
    assert digest in vecs_by_digest and len(vecs_by_digest[digest]) >= 1

    # 3) Classify using informative-chunk selection (headers not needed here)
    result = await predict_document_class(
        session=any_session,
        mode='by_chunks',
        chunk_embeddings=vecs_by_digest[digest],
        chunk_headers=None,
        m_chunk=8,
        header_weight_scale=0.0,
    )

    assert result.predicted_class == class_name
    assert result.prob > 0.5
    assert result.margin > 0.0
    assert result.chunks_used >= 1
