# Validation record — 2026-10-19

Host: Linux x86-64, Python 3.12.14, Node 24.19, FFmpeg/FFprobe 7.1.5; four CPU equivalents. No Swift compiler, Apple SDK, Mac or physical iPhone was available. These results establish portable implementation behavior, not Apple compatibility or speech-recognition quality.

## Completed checks

| Command / check | Observed outcome |
|---|---|
| `bash scripts/install.sh --all-references` with writable uv/npm caches | Completed; five original-weight manifests registered, repeated installation reuses verified assets |
| `.venv/bin/pytest -q` | 39 passed, 5 optional real-model checks skipped |
| `STT_REAL_INFERENCE=1 STT_ALL_REFERENCES=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 .venv/bin/pytest tests/test_real_inference.py -q --basetemp=.cache/reference-check` | 5 real inference checks passed; observed run took 82.64 seconds with an equivalent workspace-local temporary path |
| `.venv/bin/ruff check services tests scripts` | Passed |
| `npm --prefix apps/web run build` | TypeScript and Vite production build passed |
| `npm --prefix apps/web test` | 3 Playwright browser workflows passed against isolated live API/FFmpeg and Chromium |
| Desktop/narrow-screen visual inspection | Review and library screenshots inspected; fixture transcripts clearly labelled, no production results seeded |

The portable tests cover Unicode edit metrics, generated audio codecs/corruption, reference revisions/CAS conflicts, migrations, frozen snapshots, leases/recovery/cancellation, invalid runtime output, checksums, blind review, immutable rescoring, device ownership/disconnection paths, exports and profiling-artifact preservation. Browser checks cover import/Arabic editing/verification/history, recovery after failed save, workspace/theme states, five-output anonymous keyboard review, locking/reveal, drilldown and evaluation snapshots.

## Actual model execution

Whisper Turbo, Qwen 0.6B, Qwen 1.7B, Parakeet v3 and Ultra TDT-core/no-VAD each loaded verified original weights and executed inference on **synthetic silence in isolated temporary storage**. Integration checks traversed the actual coordinator, subprocess worker, raw-result persistence and automated scoring. Empty references retain undefined WER rather than reporting misleading zero error. Whisper additionally executed a 31-second synthetic input through sequential long-form generation; it hallucinated words on silence, which is preserved as a diagnostic observation, not an accuracy result.

Ultra's six auxiliary VAD tensors are explicitly excluded. Its processor/generation descriptors are sourced from the pinned NVIDIA v3 export with per-file provenance. Initial runs correctly failed on undeclared auxiliary tensors, a missing feature-extraction dependency and absent generation settings; the final condition resolves these explicitly. Photon segmentation and publisher-runtime parity are **not** reproduced.

Production storage contains five registered models, **zero recordings, zero experiments and zero transcription outputs**. No owner-data scores, conversion comparisons or iPhone measurements were generated. Installed model assets occupy about 12 GB and are ignored by Git.

## Unrun acceptance gates

- All native Swift builds and XCTest cases; macOS execution of Python/native adapters.
- Every physical-iPhone batch, microphone, offline, sustained, memory, thermal and lifecycle test.
- Independent conversion/quantization parity on owner recordings; all deployment accuracy rankings.
- MLX Audio and NeMo optional adapter execution, Qwen iOS integration and genuine streaming.
- Instruments/Power Profiler collection and numerical energy analysis. Trace upload support is tested; no trace-derived energy result exists.

Use `apple-validation.md` for the hardware checklist and `known-issues.md` for functional limits. Source fixes from the independent review do not substitute for compilation or device evidence.
