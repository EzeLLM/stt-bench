# Working on STT Benchmark Lab

- Use the existing checkout. Cloud tasks are already isolated; do not create a worktree unless the user requests it.
- Read `docs/architecture.md`, `docs/methodology.md`, `docs/model-compatibility.md` and `docs/known-issues.md` before changing scientific behavior.
- Core checks: `.venv/bin/pytest -q`, `.venv/bin/ruff check services tests scripts`, `npm --prefix apps/web run build`, `npm --prefix apps/web test`.
- Optional real inference check: `STT_REAL_INFERENCE=1 STT_ALL_REFERENCES=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 .venv/bin/pytest tests/test_real_inference.py -q --basetemp=.cache/reference-check`. Requires installed original weights. Never label this synthetic smoke test a speech-accuracy benchmark.
- Do not insert example results into production storage. Audio is private and local; no analytics or external audio uploads.
- Preserve raw outputs, failures, references, model identities, component precision and old evaluation scores. Version changes rather than rewriting historical evidence.
- Never equate MLX bits, Core ML LUT/linear quantization or GGUF labels. Do not call a publisher's comparison independent reference parity.
- iPhone jobs must be executed on the device; the host worker must never claim them.
- Apple compilation, physical iPhone results and Instruments measurements require actual hardware evidence. Keep unrun tests and unavailable measurements explicit.
