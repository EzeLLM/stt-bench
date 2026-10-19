---
license: apache-2.0
base_model: Qwen/Qwen3-ASR-1.7B
base_model_relation: quantized
library_name: coreml
pipeline_tag: automatic-speech-recognition
tags:
- coreml
- apple-neural-engine
- int8
- audio-encoder
- qwen3-asr
---

# Qwen3-ASR-1.7B audio encoder (Core ML, INT8)

The audio encoder of [Qwen/Qwen3-ASR-1.7B](https://huggingface.co/Qwen/Qwen3-ASR-1.7B), converted to a Core ML ML Program with INT8 weights so it can run on the Apple Neural Engine.

This repository contains only the audio encoder. Its output goes into the Qwen3-ASR-1.7B text decoder, for example the MLX build [mlx-community/Qwen3-ASR-1.7B-5bit](https://huggingface.co/mlx-community/Qwen3-ASR-1.7B-5bit). The macOS app [OpenSuperMLX](https://github.com/axot/OpenSuperMLX) downloads this model to run the encoder on the Neural Engine while the decoder runs on the GPU.

## Files

- `qwen3_asr_audio_tower_int8.mlmodelc/`: the compiled model, about 304 MB.

## Inputs and output

Each prediction encodes one 800-frame window, which is 8 seconds of 16 kHz audio at a hop length of 160.

| Name | Type | Shape | Contents |
|---|---|---|---|
| `mel` | float32 | `[1, 128, 800]` | Log-mel features computed as the base model's feature extractor does (see its `preprocessor_config.json`), zero-padded after the valid frames |
| `length` | int32 | `[1]` | Number of valid output tokens |
| `audio_features` | float32 | `[1, 104, 2048]` | Encoder output; only the first `length` rows are valid |

A full 100-frame chunk produces 13 tokens. A partial chunk of `n` frames produces `ceil(ceil(ceil(n / 2) / 2) / 2)` tokens, which is its length after three stride-2 convolutions.

For audio longer than 8 seconds, encode consecutive 800-frame windows and concatenate their valid rows. The original encoder's attention never crosses a window boundary, so the result is the same.

## How it was made

- Source weights: the BF16 audio encoder stored in mlx-community/Qwen3-ASR-1.7B-5bit, which is converted from Qwen/Qwen3-ASR-1.7B.
- Converted with coremltools 9.0 from a PyTorch 2.7.0 trace: ML Program format, float16 compute precision, weights quantized to INT8 (linear symmetric, per output channel), minimum deployment target macOS 15 / iOS 18.
- Compiled with `coremlcompiler` 3600.25.1.
- Conversion script: `Scripts/qwen3_audio_tower_coreml.py` in the OpenSuperMLX repository.

## Measurements

All measured on an Apple M1 Max running macOS 27.

- Speed: 16.3 ms per 8-second window on the Neural Engine and 59.4 ms on the CPU alone (mean of 50 predictions through coremltools).
- Accuracy, as the per-token cosine similarity with the FP32 PyTorch encoder on random inputs:

  | Window | Tokens | Worst token | Mean |
  |---|---|---|---|
  | 250 frames | 33 | 0.9976 | 0.9989 |
  | 800 frames | 104 | 0.9543 | 0.9978 |

- The JFK sample ("And so, my fellow Americans…") transcribes to the same text with this encoder as with the MLX encoder on the GPU.
- In OpenSuperMLX, transcribing a 43-second clip (Release build) with this encoder instead of the MLX encoder on the GPU: GPU busy time went from 4.97 s to 4.43 s, transcription time did not change, and peak process memory went from 2,725 MB to 2,120 MB. The Neural Engine keeps about 366 MiB wired outside the process, so the system-wide saving is about 240 MiB.

The model metadata targets macOS 15 and iOS 18, but the model has only been tested on macOS 27.

## License

Apache-2.0, inherited from Qwen/Qwen3-ASR-1.7B. The weights here are modified from that model: converted to Core ML and quantized to INT8.
