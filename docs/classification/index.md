# Classification Domain

The classification domain groups the code that predicts a document's class, manages
vector-based prototypes, and keeps an auditable history of each run. The package
is organised across data models (`models.py`), Pydantic schemas (`schemas.py`),
service helpers (`service.py`), task orchestration (`tasks.py`), and inference
logic (`inference.py`).

## Data Model Overview

- `DocClass` — catalogues every supported class and allows enable/disable without
  dropping prototypes.
- `ClassPrototype` — stores the centroid unit vector, dispersion, and document
  count that represent observed examples for each class.
- `ClassificationRun` — records the score distribution, prediction, and runtime
  configuration every time a document is classified.
- `HeaderWeight` — optional pattern matchers (literal or regex) that provide
  bonus weights when chunk headers contain informative tokens.

All models live in `src/classification/models.py` and mirror the SQLModel tables
that back them. JSON fields (e.g. prototype centroid vectors) use `model_dump(mode='json')`
when persisted.

## Services (`service.py`)

- `fetch_doc_vectors_by_digests()` pulls chunk embeddings from pgvector, collapses
  them into one unit vector per digest, and returns a dictionary keyed by digest.
- `recompute_class_prototype_batch()` rebuilds the centroid and dispersion metrics
  from a batch of labelled digests. It is the canonical way to refresh prototypes
  after importing historical labels.
- `update_class_prototype_online()` performs a fast exponential moving-average
  update when a new labelled digest arrives. The `dry_run` flag lets you preview
  the future prototype without touching the database.
- `persist_classification_run()` stores the outcome of an inference call and
  ensures the referenced `Document` exists via `metadata.service.ensure_document()`.

All service functions expect an `AsyncSession` and operate within the caller's
tenant context. Helpers such as `l2()` and `normalise_vector()` live in `utils.py`.

## Batch Trainer (`tasks.py`)

The task module exposes a Dramatiq actor `run_prototype_batch_trainer` that you
can enqueue manually or on a schedule. Under the hood it:

1. Resolves the classes to refresh (`DocClass`) and the tenant scope to scan.
2. Collects labelled digests by looking for normalised `classification` metadata
   keys inside LangChain pgvector rows (see `_LABEL_KEYS` and `_label_variants()`).
3. Calls `recompute_class_prototype_batch()` once per class with the union of
   digests across all tenants.
4. Logs a summary containing the document counts per class and which classes were
   skipped because no labels were found.

The task spins up a private event loop so Dramatiq workers can await async database
calls without blocking the main thread.

## Inference (`inference.py`)

`predict_document_class()` is the entry point used by agents and API surfaces to
score a document. It supports two modes:

- `mode="by_chunks"` — accepts raw chunk embeddings (and optional headers) and
  ranks the most informative chunks before aggregating class scores.
- `mode="by_digest"` — resolves document vectors lazily through a callback, useful
  when you only have document digests and want the service layer to fetch vectors.

The inference flow:

1. Load enabled prototypes and optional header weights from the database.
2. Normalise chunk embeddings and select the top `m_chunk` chunks based on the
   highest gap between best and second-best class scores.
3. Apply header bonuses (if configured) and average the cosine similarities.
4. Convert scores to probabilities with `softmax()`, compute the margin between
   the top classes, and return an `InferenceResult` containing the statistics.

The returned `scores` mapping is convenient for telemetry dashboards or manual
inspection when classifications need sign-off.

## Extending the Module

- **Adding classes:** insert new rows into `DocClass`, optionally pre-compute
  prototypes by seeding labelled digests and running the batch trainer.
- **Tuning prototypes:** experiment with `ema_alpha`, `m_chunk`, or
  `header_weight_scale` via configuration that your orchestrator passes into
  inference or online updates.
- **Observability:** wrap calls to `predict_document_class()` and
  `persist_classification_run()` with logging/metrics to track accuracy and drift.

Consult `src/classification/__init__.py` for the public export surface exposed to
other packages.
