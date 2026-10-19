"""Actual optional reference runtimes. No network or fallback transcriptions."""

import importlib.metadata
import json
import platform
import sys
import time
import wave
from pathlib import Path


def validate_parakeet_loading(loading: dict, model: dict) -> list[str]:
    ignored = set(loading.get("unexpected_keys", []))
    allowed = {
        f"vad_head.{component}.{kind}" for component in ("ctx", "out", "proj") for kind in ("weight", "bias")
    }
    explicit = (model.get("reference_options") or {}).get("exclude_auxiliary_vad_head", False)
    if (
        loading.get("missing_keys")
        or loading.get("mismatched_keys")
        or (
            ignored
            and not (
                explicit and model.get("repository") == "moondream/parakeet-ultra" and ignored <= allowed
            )
        )
    ):
        raise ValueError(
            "Checkpoint tensors do not exactly match this Parakeet architecture; auxiliary exclusion needs an explicit experimental condition"
        )
    return sorted(ignored)


def transcriber(request, details: dict | None = None):
    details = details if details is not None else {}
    runtime, root, settings = request["model"]["runtime"], request["model_root"], request["settings"]
    language = request["language"] if settings["language_mode"] == "forced" else None
    if language and ("+" in language or language == "mixed"):
        raise ValueError(
            "Forced language is undefined for mixed-language recordings; use automatic detection"
        )
    if runtime == "whisper-transformers":
        import numpy as np
        import torch
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

        model = AutoModelForSpeechSeq2Seq.from_pretrained(root, dtype=torch.float32, local_files_only=True)
        processor = AutoProcessor.from_pretrained(root, local_files_only=True)
        device = (
            "mps" if torch.backends.mps.is_available() else "cuda:0" if torch.cuda.is_available() else "cpu"
        )
        model.to(device)

        def run():
            with wave.open(request["audio"], "rb") as wav:
                samples = (
                    np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float32) / 32768
                )
            kwargs = {
                "task": "transcribe",
                "max_new_tokens": min(settings["max_new_tokens"], 448),
                "do_sample": settings["temperature"] > 0,
            }
            if settings["temperature"] > 0:
                kwargs["temperature"] = settings["temperature"]
            if language:
                kwargs["language"] = language
            inputs = processor(
                samples,
                sampling_rate=16000,
                return_tensors="pt",
                truncation=False,
                padding="max_length",
                return_attention_mask=True,
            ).to(device)
            # Whisper's sequential long-form algorithm, rather than the experimental independent chunk pipeline.
            with torch.inference_mode():
                tokens = model.generate(
                    input_features=inputs.input_features,
                    attention_mask=inputs.attention_mask,
                    return_timestamps=True,
                    **kwargs,
                )
            return processor.batch_decode(tokens, skip_special_tokens=True)[0]

        return run, importlib.metadata.version("transformers"), device
    if runtime == "qwen-transformers":
        import torch
        from qwen_asr import Qwen3ASRModel

        if settings["temperature"] != 0:
            raise ValueError("Qwen reference adapter currently supports greedy decoding only")
        names = {
            "en": "English",
            "tr": "Turkish",
            "ar": "Arabic",
            "de": "German",
            "zh": "Chinese",
            "fr": "French",
        }
        if language and language not in names:
            raise ValueError("This forced-language mapping is not implemented; use automatic detection")
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        model = Qwen3ASRModel.from_pretrained(
            root,
            dtype=torch.bfloat16 if device != "cpu" else torch.float32,
            device_map=device,
            max_inference_batch_size=1,
            max_new_tokens=settings["max_new_tokens"],
        )
        return (
            lambda: model.transcribe(audio=request["audio"], language=names.get(language))[0].text,
            importlib.metadata.version("qwen-asr"),
            device,
        )
    if runtime == "nemo-parakeet":
        import nemo.collections.asr as nemo_asr

        if language or settings["temperature"] != 0:
            raise ValueError("NeMo Parakeet adapter supports automatic language/greedy defaults only")
        checkpoints = list(Path(root).glob("*.nemo"))
        if len(checkpoints) != 1:
            raise ValueError("NeMo reference requires exactly one original .nemo checkpoint")
        model = nemo_asr.models.ASRModel.restore_from(str(checkpoints[0]))

        def run():
            result = model.transcribe([request["audio"]], batch_size=1)
            item = result[0] if not isinstance(result, tuple) else result[0][0]
            return item if isinstance(item, str) else item.text

        return run, importlib.metadata.version("nemo_toolkit"), str(model.device)
    if runtime == "parakeet-transformers":
        import numpy as np
        import torch
        from transformers import AutoModelForTDT, AutoProcessor

        if language or settings["temperature"] != 0:
            raise ValueError("Parakeet TDT reference supports automatic language and greedy decoding only")
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        model, loading = AutoModelForTDT.from_pretrained(
            root, dtype=torch.float32, local_files_only=True, output_loading_info=True
        )
        details["ignored_checkpoint_tensors"] = validate_parakeet_loading(loading, request["model"])
        details["max_new_tokens"] = None
        details["tdt_max_symbols_per_step"] = model.config.max_symbols_per_step
        details["segmentation"] = "full-file-attention; no auxiliary VAD"
        details["decoder_start_token_id"] = model.generation_config.decoder_start_token_id
        details["suppress_tokens"] = model.generation_config.suppress_tokens
        model.to(device).eval()
        processor = AutoProcessor.from_pretrained(root, local_files_only=True)

        def run():
            with wave.open(request["audio"], "rb") as wav:
                if wav.getframerate() != 16000 or wav.getnchannels() != 1 or wav.getsampwidth() != 2:
                    raise ValueError("Parakeet reference input must be canonical 16 kHz mono PCM16")
                samples = (
                    np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float32) / 32768
                )
            inputs = processor(samples, sampling_rate=16000, return_tensors="pt").to(device)
            with torch.inference_mode():
                result = model.generate(**inputs, return_dict_in_generate=True)
            return processor.batch_decode(result.sequences, skip_special_tokens=True)[0]

        return run, importlib.metadata.version("transformers"), device
    if runtime == "mlx-audio-qwen":
        import mlx.core as mx
        from mlx_audio.stt.utils import load_model

        mx.random.seed(request.get("seed", 0))
        model = load_model(root)

        def run():
            result = model.generate(
                request["audio"],
                max_tokens=settings["max_new_tokens"],
                language=language,
                temperature=settings["temperature"],
                stream=False,
                verbose=False,
            )
            mx.synchronize()
            return result.text

        return run, importlib.metadata.version("mlx-audio"), "Apple Silicon / MLX"
    raise ValueError(f"No Python adapter for {runtime}")


def main():
    request = json.loads(Path(sys.argv[1]).read_text())
    import random

    random.seed(request.get("seed", 0))
    if request["model"]["runtime"] != "mlx-audio-qwen":
        import torch

        torch.manual_seed(request.get("seed", 0))
    begin = time.perf_counter()
    runtime_details = {}
    run, version, device = transcriber(request, runtime_details)
    load_seconds = time.perf_counter() - begin
    for _ in range(request["settings"]["warmups"]):
        run()
    begin = time.perf_counter()
    text = run()
    inference_seconds = time.perf_counter() - begin
    if not isinstance(text, str):
        raise ValueError("Model did not produce a transcription string")
    result = {
        "text": text,
        "load_seconds": load_seconds,
        "inference_seconds": inference_seconds,
        "runtime_version": version,
        "device": device,
        "platform": platform.platform(),
        "measurement_kind": "observed",
        "loading_condition": "new-process-os-cache-uncontrolled",
        "effective_settings": {
            **request["settings"],
            "seed": request.get("seed", 0),
            "whisper_segmentation": "sequential-long-form"
            if request["model"]["runtime"] == "whisper-transformers"
            else None,
            **runtime_details,
        },
        "streaming_mode": "batch",
        "energy_joules": None,
        "first_partial_seconds": None,
    }
    print("STT_RESULT=" + json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
