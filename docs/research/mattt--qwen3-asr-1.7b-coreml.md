---
license: apache-2.0
license_link: LICENSE
base_model: Qwen/Qwen3-ASR-1.7B-hf
base_model_relation: quantized
pipeline_tag: automatic-speech-recognition
library_name: coreml
language:
- ar
- cs
- da
- de
- el
- en
- es
- fa
- fi
- fil
- fr
- hi
- hu
- id
- it
- ja
- ko
- mk
- ms
- nl
- pl
- pt
- ro
- ru
- sv
- th
- tr
- vi
- yue
- zh
tags:
- coreml
- speech-recognition
---

# Qwen3-ASR 1.7B for Core ML

This repository contains a Core ML conversion of
[Qwen3-ASR 1.7B](https://huggingface.co/Qwen/Qwen3-ASR-1.7B-hf) by the Qwen team, Alibaba Cloud,
at revision `bcd2b5b7f32b480ab5790554cfa8347f246a14f3`.
[AnySpeechRecognizer](https://github.com/mattt/AnySpeechRecognizer) runs it on Apple silicon
with the same API as Apple's `SpeechTranscriber`.

## Languages

The model transcribes speech in 30 languages: Arabic, Cantonese, Chinese, Czech, Danish, Dutch, English, Filipino, Finnish, French, German, Greek, Hindi, Hungarian, Indonesian, Italian, Japanese, Korean, Macedonian, Malay, Persian, Polish, Portuguese, Romanian, Russian, Spanish, Swedish, Thai, Turkish, Vietnamese.
It identifies the language of each segment, or the caller can set the language.
The original model card also lists 22 Chinese dialects.
This conversion was evaluated on Mandarin, Japanese, Korean, Cantonese, and English only.

## Use

```swift
let transcriber = SpeechTranscriber(
    model: QwenSpeechModel(variant: .large),
    transcriptionOptions: [],
    reportingOptions: [],
    attributeOptions: []
)
```

A version of AnySpeechRecognizer that pins this repository downloads and verifies these files
through `AssetInventory`. Other versions can load a local copy of this repository with
`QwenSpeechModel(variant: .large, assets: .directory(url))`.

## Limitations

- The model transcribes files. It does not stream, and it gives no volatile (partial) results.
  Each final result covers one segment of up to 40 seconds of audio.
- Results have no word timings, only the time range of their segment.
  The separate Qwen3-ForcedAligner-0.6B model, which predicts word timings, is not included.
- Results have no confidence values or alternatives, and the context (hotword) prompt
  of the original model is not supported.
- The language that the model identifies is not reported.
- The decoder runs on the GPU or the CPU. On macOS 27.0.1, Core ML cannot build it
  for the Neural Engine.
- The conversion was tested on a Mac with an M4 Max and macOS 27.0.1 only.
  It was not tested on iPhone or iPad.

## Size and resources

| Item | Value |
| --- | --- |
| Files | 2.36 GB |
| Peak memory while transcribing | 4.4 GB |
| Real-time factor (processing time divided by audio duration) | 0.30 to 0.36 |
| Core ML specification | iOS 18 and macOS 15 (stateful ML programs) |

The real-time factor was measured on a Mac with an M4 Max while another speech job used the GPU,
so it is higher than on an idle Mac.

## Evaluation

The table gives the error rates of AnySpeechRecognizer's runtime with this conversion
in file mode, measured on 2026-10-17 with its `Tools/natural-speech-eval.py`.
The FLEURS sets are the first 100 test files of each language.
Character error rates (CER) count characters after NFKC normalization and lowercasing,
without punctuation, symbols, or spaces.
For Cantonese, both texts are first converted to simplified characters with OpenCC,
because the references use traditional characters and the model writes either script.
Word error rates (WER) count words after lowercasing and removing punctuation.
The transformers column is the original model in transformers with greedy decoding
on the same files.

| Test set | Measure | Error rate | Substitutions / deletions / insertions | Transformers, same files | Real-time factor |
| --- | --- | --- | --- | --- | --- |
| FLEURS Mandarin (100 files) | CER | 6.28% | 57 / 136 / 27 of 3,502 | 6.25% | 0.30 |
| FLEURS Japanese (100 files) | CER | 6.10% | 209 / 51 / 48 of 5,048 | 6.08% | 0.33 |
| FLEURS Korean (100 files) | CER | 3.93% | 73 / 94 / 7 of 4,426 | 3.80% | 0.36 |
| FLEURS Cantonese (100 files) | CER | 6.25% | 172 / 17 / 31 of 3,522 | not run | 0.33 |
| LibriSpeech test-clean (252 files) | WER | 1.97% | 85 / 16 / 5 of 5,369 | 1.86% | 0.36 |
| LibriSpeech test-other (281 files) | WER | 3.46% | 139 / 28 / 12 of 5,178 | 3.40% | 0.35 |

The FLEURS references write numbers as digits, names in Latin script,
and some English glosses in parentheses that speakers did not always read.
The model often writes numbers in words and names in the local script,
so these error rates are higher than those in the original model card.

## Conversion and verification

The models were converted with this command in `Tools/QwenConversion`:

```sh
uv run python convert.py --variant 1.7b --dtype float16
```

The tools were Python 3.12.12, PyTorch 2.8.0, transformers 5.20.0,
and coremltools 9.0 on macOS 27.0.1.
The KV cache holds 1,024 tokens, and the decoder takes
16 tokens in each prediction.

`Tools/QwenConversion/verify.py` compared the conversion with the transformers model.
It compared the audio embeddings for each token,
the decoder's greedy token after each prefix of the transformers output,
and complete greedy transcripts.

| Model | Clips | Encoder mean / lowest token cosine | Decoder tokens that match, teacher-forced | Transcripts identical to `generate()` |
| --- | --- | --- | --- | --- |
| PyTorch wrappers (before Core ML) | 8 synthetic speech (`say`) | 1.00000 / 1.000 | 313 of 313 | 8 of 8 |
| Core ML, CPU_AND_GPU | 8 synthetic speech (`say`) | 0.99899 / 0.710 | 312 of 313 | 8 of 8 |
| Core ML, CPU_AND_GPU | 16 FLEURS and LibriSpeech | 0.99892 / 0.718 | 558 of 562 | 14 of 16 |

The two differing transcripts differ only in word spacing in Korean ("마무리되었으며" for "마무리 되었으며", "북발트해" for "북 발트해").

## Files

| File | Size |
| --- | --- |
| `AudioEncoder.mlmodelc` | 318.6 MB |
| `LICENSE` | 11.3 kB |
| `NOTICE` | 1.8 kB |
| `TextDecoder.mlmodelc` | 2,034.9 MB |
| `qwen3_asr_config.json` | 5.5 kB |
| `vocab.json` | 2.3 MB |

`conversion.json` lists the size and SHA-256 digest of every file except itself and this card.

## License

The original model and this conversion are licensed under the
[Apache License, Version 2.0](https://www.apache.org/licenses/LICENSE-2.0). See `LICENSE` and `NOTICE`.

Qwen3-ASR 1.7B by the Qwen team, Alibaba Cloud (https://huggingface.co/Qwen/Qwen3-ASR-1.7B-hf), licensed under the Apache License, Version 2.0 (https://www.apache.org/licenses/LICENSE-2.0). Converted to Core ML for AnySpeechRecognizer: the model is split into an audio encoder and a text decoder with a KV cache, weights are stored in float16, and weights of large layers are quantized to int8.
