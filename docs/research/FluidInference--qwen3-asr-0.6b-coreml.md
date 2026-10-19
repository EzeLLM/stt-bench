
---
license: apache-2.0
language:
  - en
  - zh
  - ja
  - ko
  - vi
  - th
  - id
  - ms
  - hi
  - ar
  - tr
  - ru
  - de
  - fr
  - es
  - multilingual
tags:
  - speech-recognition
  - asr
  - coreml
  - apple
  - ios
  - macos
  - qwen
  - audio
library_name: coreml
pipeline_tag: automatic-speech-recognition
base_model: Qwen/Qwen3-ASR-0.6B
---

# Qwen3-ASR 0.6B CoreML

Core ML conversion of [Qwen/Qwen3-ASR-0.6B](https://huggingface.co/Qwen/Qwen3-ASR-0.6B) for
on-device speech recognition on Apple platforms (iOS/macOS).

## Model Variants

| Variant | Size | Description |
|---------|------|-------------|
| `f32/` | ~2.5 GB | Full precision (Float32) - highest accuracy |
| `int8/` | ~0.7 GB | Quantized (Int8) - smaller, faster |

## Features

- **30+ languages** including English, Chinese, Japanese, Korean, and more
- **On-device inference** - no internet required
- **Autoregressive decoder** with KV-cache support
- Processes audio in 1-second chunks (100 mel frames)

## Benchmarks (M4 Pro)

| Dataset | WER | CER | RTFx |
|---------|-----|-----|------|
| LibriSpeech test-clean (2620 files) | 4.4% | 1.9% | 2.8x |
| AISHELL-1 test (100 files) | 4.6% | 3.7% | 4.5x |

*Official PyTorch model: 2.11% WER on LibriSpeech test-clean*

## Usage with FluidAudio

```
import FluidAudio

let manager = Qwen3AsrManager()
try await manager.loadModels()

let samples = try AudioConverter().resampleAudioFile(path: "audio.wav")
let transcript = try await manager.transcribe(
    audioSamples: samples,
    language: "en",
    maxNewTokens: 512
)
print(transcript)
```


Model Architecture

- Encoder: Audio encoder (Whisper-style mel spectrogram input)
- Decoder: 28-layer transformer decoder with 1024 hidden size
- Tokenizer: Qwen tokenizer with special ASR tokens


License

Apache 2.0 - Same as the original Qwen3-ASR model.

Credits

- Original model: https://huggingface.co/Qwen/Qwen3-ASR-0.6B by Alibaba Qwen Team
- Paper: https://arxiv.org/abs/2601.21337
- CoreML conversion: https://github.com/FluidInference/FluidAudio

Citation

@article{qwen3asr,
  title={Qwen3-ASR Technical Report},
  author={Qwen Team},
  journal={arXiv preprint arXiv:2601.21337},
  year={2025}
}
  
For the HuggingFace metadata UI, fill in:
- **License**: Apache 2.0
- **Base model**: Qwen/Qwen3-ASR-0.6B
- **Pipeline**: automatic-speech-recognition
- **Library**: coreml
- **Languages**: en, zh, ja, ko, + others