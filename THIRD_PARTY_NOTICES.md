# Third-party provenance

Project code is Apache-2.0. Dependencies retain their own licenses. They are installed through package managers rather than copied into project source.

`docs/research/` preserves primary-source material for reproducible compatibility investigation, including:

- QwenLM/Qwen3-ASR documentation and license: Apache-2.0, Qwen/Alibaba contributors.
- FluidInference/FluidAudio documentation and inspected source excerpts: Apache-2.0. Its full license is preserved in that directory.
- Argmax WhisperKit documentation and inspected source: MIT, Copyright (c) 2024 argmax, inc.; the full license is preserved in that directory.
- MLX/MLX Swift/MLX Audio and community model documentation, subject to their source repository licenses.
- AnySpeechRecognizer documentation from mattt, subject to its repository license.
- Hugging Face model metadata/cards from the original/conversion publishers, with exact revisions and license metadata recorded. NVIDIA Parakeet v3 and Moondream Parakeet Ultra weights/conversions carry CC-BY-4.0 metadata; preserve attribution and modification history when distributing weights. FluidAudio's Apache code license does not replace the weight license.
- Apple Power Profiler documentation, linked to its original Apple Developer page and retained as research evidence. Apple trademarks and documentation remain Apple's property.

Installed weights, recordings, dependency caches and generated binaries are ignored and are not included in the source repository. Research copies are evidence, not claims that the lab authors created or independently validated those upstream implementations.
