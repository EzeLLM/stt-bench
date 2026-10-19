# STT Benchmark Lab architecture

Status: implementation in progress. This document is the authoritative local-system design; see `implementation-status.md` for evidence rather than inferred readiness.

## Intent and constraints

A private, single-researcher workbench compares model/checkpoint/backend combinations on the owner's recordings. Two distinct workloads share immutable input and result identities: reference/deployment accuracy on Mac, and entirely local inference on a physical iPhone. No public evaluation datasets, fabricated results, remote iPhone inference, analytics, or automatically accepted ground truth. Test fixtures are generated tones or tiny textual examples, never project evaluation data.

## Decisions

Use React/TypeScript/Vite with TanStack Table and accessible Radix primitives. FastAPI owns SQLite in WAL mode, numbered transactional migrations, audio storage, and a versioned `/api/v1` API. An independent worker claims jobs transactionally with leases. SQLite is the source of truth; JSON is for manifests, snapshots, interchange and exports, never a substitute for transactional job state.

Alternatives considered: a desktop Electron shell adds distribution work without improving the first browser-based workflow; a Python-only UI limits dense keyboard review. A hosted inference service violates privacy and device-measurement requirements. Native SwiftUI shares an Apple inference package with a JSON-line macOS runner.

## Data and trust boundaries

Originals are immutable content-addressed files. Canonical inputs are lossless 16 kHz mono signed PCM WAV, created directly from the original once using a versioned FFmpeg command. Source SHA-256, output SHA-256, FFmpeg version, command, metadata, waveform and diagnostic thresholds are recorded. No enhancement, loudness changes or VAD by default. Model-specific preprocessing belongs in the runtime snapshot.

References have append-only revisions with draft/verified state, a current-revision pointer and optimistic concurrency. Initial reference editing never displays predictions. Experiment creation snapshots verified text, revision, labels, language, processed asset hash, model manifest and decoder configuration. Later corrections mark historical results stale; rescoring creates a new evaluation snapshot. Finalized experiments reject mutations.

Jobs have explicit queued/running/succeeded/failed/cancelled states, preserved attempts, deadlines and recoverable leases. Invalid runner output fails the attempt. Cancellation terminates only the worker's own child process. A restart records an interrupted attempt before retry. iPhone jobs are never claimed by the Mac worker.

Checkpoint candidates are distinct from installed verified manifests. A manifest requires exact repository commit, license, source identity, per-file SHA-256, component precision, backend/runtime version and local assets. Unknown facts remain unknown. An installed manifest does not establish reference parity or physical-device compatibility. No bit-width equivalence between MLX, GGUF and Core ML.

## Evaluation

Versioned `unicode-v2` uses NFC, whitespace folding, Unicode punctuation replacement and language-aware casing (explicit labels containing tr use Turkish casing; generic mixed uses Unicode casing). Arabic letters and diacritics are retained; no transliteration, alef folding or lexical substitutions. Strict NFC metrics remain separate. WER uses whitespace-delimited words; CER uses Unicode grapheme clusters including internal spaces after whitespace folding. Empty references have undefined rates and explicit insertion counts. Corpus WER/CER use summed edit counts and denominators. Confidence intervals resample recordings, paired for deployment-minus-reference comparisons; repeated inference does not create independent recordings.

Blind review uses a persisted seed, per-recording randomized anonymous output IDs, identical presentation, no model metadata/score/timing, complete tie-capable rankings and separate subjective dimensions. Mapping is returned only after locking. This prevents incidental UI leakage, not access by the owner inspecting their own database.

## API and execution

`/recordings` imports/lists; recording resources expose audio, metadata, labels, reference history. `/models` lists candidates and registered manifests. `/experiments` previews/creates fixed snapshots; actions start/pause/cancel/resume/retry/finalize. `/experiments/{id}/jobs` and `/events` provide persisted progress. `/reviews` creates and saves blind sessions. `/compare` aggregates stored snapshots and exposes drilldown IDs. `/exports` and `/backup` preserve raw evidence.

Coordinator binds loopback by default. LAN access requires an explicit token and user-selected bind address. Device registration/claim/result APIs authenticate a paired device, hash inputs and preserve idempotent result submissions. Device jobs require device identifiers and measurement envelopes; no endpoint forwards iPhone audio to a Mac inference adapter. Local Wi-Fi HTTP pairing is for trusted LANs; TLS is required on untrusted networks.

## Apple feasibility and measurement

Swift package targets iOS 17/macOS 14 where FluidAudio is used. WhisperKit and FluidAudio are pinned to inspected source revisions. Native batch APIs are not called true streaming. No automatic model downloads during measurement; assets are staged and hashed first. ContinuousClock measures loading and inference; runtime memory observations, battery and thermal state are labelled observations, not numerical energy. Instruments traces remain external artifacts. Swift source compilation and physical-iPhone acceptance are hardware gates, unavailable on this Linux host.

Qwen Python reference support and Python MLX support do not establish Swift architecture support. Qwen Core ML parity, complete conversion and mobile feasibility stay blocked pending primary evidence and paired tests. Every adapter is capability gated.

## UX

One compact application shell: Library, Experiments, Review, Compare, Devices and registry. Library uses a table plus inspector, waveform/playback, independent reference editing and explicit autosave state. Review keeps a recording queue and stacked readable transcripts in one viewport, with a collapsible inspector. Neutral slate surfaces, teal actions, restrained error colors, 14–16 px body text, tabular metrics, light/dark themes, keyboard navigation and `dir=auto` transcript fields. Production empty states contain no example results.

## Validation gates

Required here: audio import across generated codec fixtures; corruption/duplicates; Turkish/Arabic/mixed-script normalization and known alignments; optimistic reference conflicts; transactional recovery; snapshot immutability; real subprocess failure/cancellation; blindness and locking; API/build/browser workflows. Required externally: original checkpoint downloads and hashes, inference on owner speech, Mac build and runtime, physical iPhone offline batch/live/sustained execution, reference parity, Instruments profiling. Those external gates cannot be replaced with mocked success.
