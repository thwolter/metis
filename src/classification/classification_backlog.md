# Classification: Implementation & Backlog

## Implemented now
- **KNN + informative‑chunk selection** with optional **header‑weights boost**.
  - Module: `src/classification/inference.py`
  - API:
    ```py
    from classification.inference import predict_document_class, InferenceResult

    result: InferenceResult = await predict_document_class(
        session=any_session,                 # AsyncSession
        chunk_embeddings=list[np.ndarray],   # per‑chunk vectors (any dim)
        chunk_headers=list[str|None] | None, # optional markdown headers per chunk
        m_chunk=8,                           # informative chunk count
        header_weight_scale=0.05,            # scale for header bonuses
    )
    ```
  - Decision rule: cosine to class centroids (+ header bonus) → pick **top‑m** informative chunks by best‑vs‑second gap → average per‑class scores → softmax prob, margin.

- **Tests**
  - File: `tests/integration_tests/test_inference.py`
  - Cases:
    1) Header boosts favour the correct class.
    2) Informative‑chunk selection works without header boosts.

## Next Items (backlog)
1. **Public API Endpoints (FastAPI)**
   - `POST /api/classification/recompute`, `POST /api/classification/online-update`, `POST /api/classification/predict`.
   - Auth: Bearer; DB read under `classifier_service` via `SET LOCAL ROLE`.

2. **Persist Classification Runs**
   - Insert into `classification.classification_runs` on every prediction (`config`, `prob`, `margin`, `chunks_used`).

3. **Thresholds & Abstain**
   - Per‑class/global thresholds (`min_margin`, `min_prob`, `min_chunks`); return `abstain` when below thresholds.

4. **Batch Trainer Job**
   - Recompute prototypes daily/on demand from labelled digests.

5. **Metrics & Monitoring**
   - Prometheus: `predictions_total`, `low_margin_total`, `avg_margin`.
   - Drift: rolling mean of `(1 − cos(dvec, mu))` per class with alerting.

6. **Caching**
   - Redis for `(digest → vector)`; cache prototypes with TTL, invalidate on update.

7. **Admin Endpoints**
   - Manage classes and prototypes (enable/disable, manual override).

8. **Docs**
   - API contract, ops runbook (RLS role switch), decision logic, seed guidance.
