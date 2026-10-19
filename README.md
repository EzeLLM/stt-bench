# STT Benchmark Lab

A private, local research workbench for comparing speech-recognition **models, checkpoints, conversion paths and runtimes** on your own recordings. React research UI, FastAPI/SQLite coordinator, isolated reference runners and an experimental native SwiftUI client.

**Current release is a research build, not a completed, device-validated product.** The Linux dataset/evaluation/web workflow and original weights from all five model families have been exercised. Ultra uses an explicitly separate TDT-core/no-VAD condition, not its published Photon pipeline. Native Apple code is authored but has not been compiled on macOS or run on an iPhone. Qwen iOS integration remains a compatibility investigation. See [implementation status](docs/implementation-status.md) and [known issues](docs/known-issues.md).

## Start locally

Prerequisites: Python 3.12+, uv, Node 24+, npm, FFmpeg and FFprobe. On a Mac install the tools through your usual trusted package manager; native builds additionally need Xcode, Swift 6 and XcodeGen.

```bash
bash scripts/install.sh                 # coordinator, web UI, build and tests
bash scripts/install.sh --reference     # also stage the pinned original Whisper Turbo (~1.6 GB)
bash scripts/install.sh --all-references # Linux: stage all five originals (~12 GB assets)
.venv/bin/python scripts/dev.py         # supervises coordinator, worker and Vite
```

Vite prints the local browser address. The coordinator uses port 8000; Vite uses port 5173. The default bind is loopback. Stop the supervisor with Ctrl-C. The SQLite worker recovers expired leases on restart; runtime processes are not assumed to survive a new task.

For trusted LAN pairing, run `scripts/dev.py --lan`, open Devices in the desktop UI, and enter the Mac's LAN address and local pairing token in the iPhone app. Device credentials live in the phone's Keychain. Desktop APIs remain local; device endpoints require their own token. Use TLS on untrusted networks. No server endpoint performs inference for an iPhone job.

## Workflows

1. **Library:** bulk drop or choose Voice Memos/audio files. Originals remain unchanged; canonical 16 kHz mono PCM WAV, metadata, hashes, waveform and diagnostic thresholds are recorded. Label language and tags, independently write ground truth, and explicitly verify it. Autosave uses revision checks; a failed save retains a browser-local recovery draft.
2. **Registry:** stage exact model assets, then register a JSON manifest with revision, license, runtime, component precisions and every file hash. Candidates are research leads, not runnable assets. The five original-weight implementations can be prepared using `--all-references` above; converted Apple assets are installed separately.
3. **Experiments:** select verified recordings and installed implementations. Preview compatible jobs, freeze an experiment, then start it. The separate worker handles host jobs. Failed attempts, cancellation and retries remain distinguishable.
4. **Review:** anonymous, seeded per-recording ordering hides identities, scores and timing. Save subjective dimensions, comments and complete tie-capable ranks. Lock before revealing. J/K changes recording, arrows select output, and 1–5 sets faithfulness when focus is outside an input.
5. **Compare:** corpus WER/CER, strict/normalized text, category/language filters, uncertainty, failure coverage, runtime distributions and paired deployment penalties. Click a row for the actual recordings. Corrected references can create a new evaluation snapshot; original scores stay unchanged.
6. **Devices:** pair the experimental native app, stage model assets and benchmark inputs, execute locally with Wi-Fi disconnected, and later synchronize. Power traces are external artifacts, never invented joule measurements.

The application starts without sample recordings or fabricated leaderboards. Synthetic tests live in temporary databases and never populate `data/recordings` or the production library.

## Model installation and actual inference

[Model setup](docs/models.md) explains manifests, reference environments, native asset layout, licenses and the corrected Parakeet encoder. [Compatibility findings](docs/model-compatibility.md) links exact primary sources, including the Qwen Core ML accuracy discrepancy and newer Qwen 1.7B conversion.

The original Whisper adapter uses Transformers' sequential long-form generation with FP32 compute from the pinned original checkpoint. The official `qwen-asr` adapter and Transformers TDT adapter have also executed locally with the pinned originals. Ultra explicitly excludes its six auxiliary VAD tensors and records processor/generation descriptors borrowed from the pinned NVIDIA v3 source. This establishes execution, not accuracy or publisher-runtime parity. Optional NeMo and MLX Audio adapters remain unexecuted. MLX Audio and qwen-asr currently require incompatible Transformers major versions, so do not combine those environments.

```bash
# Validate the actual coordinator → worker → original model → persisted score path.
# Uses isolated synthetic silence, not your evaluation dataset; takes CPU time.
STT_REAL_INFERENCE=1 STT_ALL_REFERENCES=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 \
  .venv/bin/pytest tests/test_real_inference.py -q --basetemp=.cache/reference-check
```

## Build the iPhone app on a Mac

```bash
cd runners/apple-native
swift test
swift build -c release
cd ../../apps/ios
xcodegen generate
open STTBenchmarkLab.xcodeproj
```

Choose your signing team and physical iPhone in Xcode. The base app requires iOS 17+. Its supported source adapters are WhisperKit and FluidAudio; both remain unvalidated in this project. Qwen conversion artifacts are not interchangeable with these adapters. See [Apple validation](docs/apple-validation.md) for mandatory build, offline, cancellation, load, thermal and profiling checks.

## Verify and export

```bash
.venv/bin/pytest -q
.venv/bin/ruff check services tests scripts
npm --prefix apps/web run build
npm --prefix apps/web test
```

Browser tests use a fresh temporary database, a real API and FFmpeg. They include synthetic transcripts explicitly labelled as UI fixtures. CI runs the portable suite; it does not claim Apple compatibility or download public speech datasets.

Use **Back up dataset** for a consistent SQLite snapshot with originals, processed audio and profiling artifacts. Backups exclude model binaries and pairing credentials. JSON exports include raw predictions, attempts, reference snapshots, evaluation revisions and locked/unlocked review evidence; CSV is a compact job summary. Keep backups private. Restage model assets by their manifests when restoring on another machine.

## Structure

```text
apps/web/                    React/TypeScript research UI
apps/ios/                    SwiftUI app + transactional local journal
services/coordinator/stt_lab/ SQLite, API, datasets, scoring, jobs and Python adapters
runners/apple-native/        Local-only WhisperKit/FluidAudio package and macOS CLI
packages/protocol/            Generated versioned OpenAPI contract
scripts/                     Repeatable install, asset verification and supervision
docs/                        Architecture, methodology, evidence and validation gates
tests/                       Isolated scientific, audio, recovery and protocol tests
data/                        Private ignored storage; never commit recordings or weights
```

The Python responsibilities are modules in one installable package to keep migrations and worker imports consistent. Native and browser boundaries stay independent through the API and versioned envelopes.

Project code is Apache-2.0. Model and runtime licenses differ; see [third-party notices](THIRD_PARTY_NOTICES.md).
