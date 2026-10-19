---
license: apache-2.0
base_model: Qwen/Qwen3-ASR-1.7B
tags:
  - coreml
  - asr
  - speech-to-text
  - qwen3
  - on-device
  - apple
  - macos
language:
  - zh
  - en
  - ja
  - ko
  - multilingual
pipeline_tag: automatic-speech-recognition
library_name: coremltools
---

# Qwen3-ASR-1.7B CoreML

CoreML conversion of [Qwen/Qwen3-ASR-1.7B](https://huggingface.co/Qwen/Qwen3-ASR-1.7B) for on-device speech-to-text on macOS/iOS.

Optimized with **FP32 compute + ANEMLL RMSNorm + mixed-precision INT8** to prevent decoder overflow while keeping model size small.

## Files

| File | Description | Size |
|------|-------------|------|
| `qwen3_asr_encoder_int8.mlpackage/` | Audio encoder (Conv2D + 24-layer Transformer + projection). FP16 compute, INT8 per-channel weights. | 304 MB |
| `qwen3_asr_decoder_f32_anemll_int8-mixed.mlpackage/` | Decoder (28-layer causal LLM + LM head). FP32 compute, ANEMLL RMSNorm, mixed-precision INT8. | 2.8 GB |
| `qwen3_asr_embeddings.bin` | Token embedding table (FP16, shape 151936 x 2048). Loaded separately to avoid quantizing embeddings. | 594 MB |

## Architecture

```
Audio (16kHz) → Mel Spectrogram (128 bins)
  → Encoder (100-frame chunks → 13 tokens each)
  → Embedding lookup + prompt construction
  → Decoder (autoregressive, RoPE as inputs, KV cache)
  → Token IDs → Text
```

### Encoder

- 3x Conv2D (stride 2) + 24-layer Transformer + 2-layer projection
- Input: `[1, 1, 128, 100]` mel chunk → Output: `[1, 13, 2048]` audio features
- Bidirectional attention, sinusoidal positional embeddings (reset per chunk)
- INT8 per-channel quantization (first conv layer kept at FP16)

### Decoder

- 28-layer causal Transformer with GQA (16 Q heads, 8 KV heads, head_dim=128)
- SwiGLU MLP (intermediate_size=11008)
- RoPE theta=1,000,000 (NeoX/split-half style, passed as cos/sin inputs)
- ANEMLL-style RMSNorm: `LayerNorm([x, -x])` trick for numerical stability
- Mixed-precision INT8: first/last layer, norms, LM head kept at FP16

### Key Quality Improvements

1. **FP32 compute for decoder** — Hidden states reach 10,876 at layer 25; x^2 = 118M >> FP16 max 65,504. FP32 is mandatory.
2. **ANEMLL RMSNorm** — Uses native `layer_norm` op via `[x, -x]` concatenation for GPU/ANE precision.
3. **Mixed-precision INT8** — Skips 72 sensitive ops (embeddings, first/last layer, all norms, LM head).
4. **RoPE as inputs** — Precomputed sin/cos passed in to avoid in-model precision loss.
5. **Embeddings extracted** — 151,936-token embedding table stored as raw FP16 binary, not quantized.

## Quality Benchmarks

### English (JFK speech, 11s)

| Pipeline | Transcription | Match |
|----------|---------------|-------|
| PyTorch FP32 | "And so, my fellow Americans, ask not what your country can do for you. Ask what you can do for your country." | Reference |
| CoreML INT8 | Same text (minor punctuation difference: "." vs ";") | **MATCH** |

### Taiwan Mandarin (Taiwan-Tongues test set, 20 samples, 60s total)

| Metric | Value |
|--------|-------|
| PyTorch vs CoreML match rate | **19/20 (95%)** |
| Average CER (PyTorch) | 0.2009 |
| Average CER (CoreML INT8) | 0.2064 |
| CER difference | **+0.0056** |

## Usage Notes

- **macOS 14+** required (minimum deployment target)
- Decoder runs on **GPU only** (FP32 compute prevents ANE execution)
- KV cache must be initialized with **1 dummy slot** (CoreML crashes on size-0 dynamic dims); mask the dummy position with `-inf`
- Encoder processes mel in **100-frame chunks** — split mel, run encoder per chunk, concatenate outputs

## Conversion Details

Converted using `coremltools 9.0` with PyTorch 2.10.0. Conversion scripts available at the source repository.

```
compute_precision: FLOAT32 (decoder), FLOAT16 (encoder)
minimum_deployment_target: macOS14
quantization: linear_symmetric INT8 per-channel (mixed-precision for decoder)
```

## License

Apache 2.0 (same as base model)
