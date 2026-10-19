# Checkpoint setup

`stt_lab/data/catalog.json` records the inspected candidates and exact primary repository revisions. A candidate is not an installation. `docs/research/` contains captured model cards, metadata, runtime source, issue reports, checksums and provenance.

The portable ready-to-run path is:

```bash
bash scripts/install.sh --reference
```

This stages `openai/whisper-large-v3-turbo` at `41f01f3fe87f28c78e2fbf8b568835947dd65ed9`. The weight file is verified against its upstream SHA-256 `542566a422ae4f3fd23f1ba11add198fca01bbf82e66e6a2857b3f608b1eb9d1`. Small files are verified against their Git blob IDs and recorded with SHA-256. FP16 source weights are upcast to FP32 compute. No converted checkpoint is silently substituted.

## Five original-weight implementations on Linux

```bash
bash scripts/install.sh --all-references
```

This installs three isolated Python environments (`.venv-reference`, `.venv-qwen`, `.venv-parakeet`) from version-pinned Linux/Python3.12 dependency snapshots and official CPU Torch wheels. It stages about 12 GB of original assets, verifies their upstream identities and SHA-256, then registers immutable manifests. Repeating installation reuses verified assets. Downloads never contain evaluation audio. Additional environment/cache space is required; provision at least 20 GB free for a clean setup. Mac installation of these extra environments has not been validated.

Qwen uses the official qwen-asr package. Parakeet v3 uses the original current Transformers TDT export. Ultra's card reports results through Photon on NVIDIA GPUs; this project's separate `parakeet-ultra-tdt-core-no-vad-fp32` condition runs its TDT core and **explicitly excludes the six auxiliary VAD tensors**. The original tensors stay on disk and are hash checked. The loader rejects every unexplained missing/mismatched/unexpected tensor. Ultra lacks Transformers processor and generation descriptors, so those three small files come from the pinned NVIDIA v3 repository, with per-file source/revision in the manifest. Generation starts with blank and suppresses duration-only logits as specified there. This is a legitimate no-VAD experimental implementation, not a reproduction of Photon or evidence of reference parity. Compare on owner recordings before making model-quality claims.

All five executed synthetic silence locally. Passing a smoke check means the inference/result/scoring path works; it does not mean speech accuracy, quantization parity or Apple compatibility is validated.

## Other checkpoints

Stage selected files without downloading an entire multi-model repository:

```bash
.venv/bin/python scripts/fetch_checkpoint.py \
  --repository OWNER/REPOSITORY --revision FULL_40_CHARACTER_COMMIT \
  --destination data/models/UNIQUE_VARIANT \
  --include 'SELECTED_COMPONENT/*' --include 'REQUIRED_TOKENIZER_FILE' \
  --output data/UNIQUE_VARIANT-inventory.json
```

The helper retains TLS checks and verifies SHA-256 for LFS objects or Git blob identity for small files. It never downloads evaluation audio. An inventory alone is not a runnable manifest: complete the model's provenance and component precision first. Inspect the exact repository layout rather than copying generic filenames.

See the generated OpenAPI `Manifest` schema in `packages/protocol/openapi.json`. Required fields include id, family, variant, repository, immutable revision, license, original/conversion publisher, source checkpoint, runtime/runtime version, root relative to `data`, languages, component precision/quantization and every file's hash. `parameter_count` and observed runtime memory remain null until established. Record conversion procedure, published comparisons and known issues when available. Never invent an original parameter count from a nominal family name.

`root` must stay inside the storage directory. Every checkpoint file must be declared. Registered IDs are immutable; use a new ID for another conversion, decoder policy or precision. To register:

```bash
.venv/bin/python -m stt_lab.cli register-model data/VARIANT-manifest.json
```

Alternatively choose **Register manifest** in the registry. Checkpoint assets must already exist locally; the browser upload registers metadata, not model bytes. The installed original's `data/whisper-reference-manifest.json` is a concrete example.

## Runtime environments

`executable` selects the Python interpreter or native CLI; it is configured by the local researcher, never supplied by an iPhone job. The worker uses argument arrays, not shell commands. Model assets are hashed again before inference. Runtime-version mismatch or malformed output fails the attempt.

| Runtime | Entry point | Dependencies / status |
|---|---|---|
| `whisper-transformers` | `stt_lab.runners` | Pinned Transformers 4.57.6/Torch 2.8 reference environment. Actual Linux inference tested. |
| `qwen-transformers` | same module | qwen-asr 0.0.6, Transformers 4.57.6, Accelerate 1.12.0 and its declared dependencies. Linux CPU FP32 executed for both original sizes. CUDA BF16 path untested. |
| `parakeet-transformers` | same module | Transformers 5.20.1, Torch 2.8 and Librosa 1.0.0 in an isolated environment. Original v3 and explicit Ultra TDT-core/no-VAD Linux runs exercised. |
| `nemo-parakeet` | same module | Compatible NeMo ASR environment and exactly one original `.nemo` checkpoint. Source adapter; not executed here. Automatic/greedy mode only. |
| `mlx-audio-qwen` | same module | Apple Silicon, MLX Audio; inspected current 0.5.9 requires Transformers ≥5.14 and MLX ≥0.31.1. Use a separate environment from qwen-asr. Not executed here. |
| `whisperkit` | `stt-native` | Pinned WhisperKit revision. Requires Mac build and physical-device validation. |
| `fluidaudio` | `stt-native` | Pinned FluidAudio revision. Requires Mac build and physical-device validation. |

Python runner output is one `STT_RESULT=` JSON envelope with raw text, monotonic load/inference timing, exact runtime version, actual platform and effective settings. No stub production runtime exists. Missing dependencies fail explicitly. The reference install avoids GPU wheel downloads on Linux.

## Native asset requirements

WhisperKit: stage the selected Turbo/626MB compiled model components plus the matching original tokenizer JSON/config files in the local model root. Hash every file and record the tokenizer source checkpoint revision. The native loader requires those local tokenizer files and disables model downloading; verify offline behavior on the physical device before accepting performance evidence.

FluidAudio: stage `Preprocessor.mlmodelc`, the explicitly selected encoder, `Decoder.mlmodelc`, `JointDecisionv3.mlmodelc` and `parakeet_vocab.json`. Use `AsrModels.loadLocal`, not auto-recovery/download helpers. For v3, choose `native_options.encoder_precision="int8-v2"` to select `Encoder_v2.mlmodelc`. The API name `int8` loads the historical 6-bit LUT `Encoder.mlmodelc`; do not label it linear INT8. Ultra uses its own INT8 encoder.

Native runtime version strings must match the compiled package revisions:

```text
WhisperKit/9f99b5cb6a907730543823ad271b82532782a899
FluidAudio/2d6c42ca5f3accc0faf9fee9e0fff5b9b2cf6042
```

Use `native_options.compute_units` to explicitly choose `cpuOnly`, `cpuAndGPU`, `cpuAndNeuralEngine` or `all`. The Whisper mel frontend uses CPU/GPU; the encoder and decoder use that requested option. These are requested placements, not proof of actual ANE execution; profile actual hardware.

No native Qwen adapter is enabled in the iOS 17 app. The newer AnySpeechRecognizer candidate requires Swift 6.2 and iOS/macOS 26+, has its own tokenizer/decoder pipeline, and needs a separate integration and parity study.
