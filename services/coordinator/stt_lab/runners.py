"""Actual optional reference runtimes. No network or fallback transcriptions."""

import importlib.metadata
import json
import platform
import sys
import time
import wave
from pathlib import Path

# Longest decoder prefix: start-of-transcript, language, task, no-timestamps.
WHISPER_MAX_PREFIX_TOKENS = 4


def whisper_max_new_tokens(requested: int, max_target_positions: int) -> int:
    """Whisper's decoder positions are shared by the prefix tokens and the generated tokens."""
    return min(requested, max_target_positions - WHISPER_MAX_PREFIX_TOKENS)


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


QWEN_LANGUAGE_NAMES = {
    "en": "English",
    "tr": "Turkish",
    "ar": "Arabic",
    "de": "German",
    "zh": "Chinese",
    "fr": "French",
}


def item_language(runtime: str, settings: dict, item: dict):
    """The forced language for one recording, or None for automatic detection."""
    language = item["language"] if settings["language_mode"] == "forced" else None
    if language and ("+" in language or language == "mixed"):
        raise ValueError(
            "Forced language is undefined for mixed-language recordings; use automatic detection"
        )
    if runtime == "qwen-transformers" and language and language not in QWEN_LANGUAGE_NAMES:
        raise ValueError("This forced-language mapping is not implemented; use automatic detection")
    if runtime == "nemo-parakeet" and language:
        raise ValueError("NeMo Parakeet adapter supports automatic language/greedy defaults only")
    if runtime == "parakeet-transformers" and language:
        raise ValueError("Parakeet TDT reference supports automatic language and greedy decoding only")
    return language


def transcriber(request, details: dict | None = None):
    """Load a model once. The returned run(item) transcribes one recording with that loaded model."""
    details = details if details is not None else {}
    runtime, root, settings = request["model"]["runtime"], request["model_root"], request["settings"]
    item_language(runtime, settings, request)  # fail before the expensive load
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

        def run(item):
            language = item_language(runtime, settings, item)
            with wave.open(item["audio"], "rb") as wav:
                samples = (
                    np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float32) / 32768
                )
            kwargs = {
                "task": "transcribe",
                "max_new_tokens": whisper_max_new_tokens(
                    settings["max_new_tokens"], model.config.max_target_positions
                ),
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
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        model = Qwen3ASRModel.from_pretrained(
            root,
            dtype=torch.bfloat16 if device != "cpu" else torch.float32,
            device_map=device,
            max_inference_batch_size=1,
            max_new_tokens=settings["max_new_tokens"],
        )
        return (
            lambda item: (
                model.transcribe(
                    audio=item["audio"],
                    language=QWEN_LANGUAGE_NAMES.get(item_language(runtime, settings, item)),
                )[0].text
            ),
            importlib.metadata.version("qwen-asr"),
            device,
        )
    if runtime == "qwen-native-transformers":
        import numpy as np
        import torch
        from transformers import AutoModelForMultimodalLM, AutoProcessor

        if settings["temperature"] != 0:
            raise ValueError("Native Qwen3-ASR reference uses deterministic decoding")
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        processor = AutoProcessor.from_pretrained(root, local_files_only=True)
        model = (
            AutoModelForMultimodalLM.from_pretrained(root, dtype=torch.float32, local_files_only=True)
            .to(device)
            .eval()
        )
        details["num_beams"] = model.generation_config.num_beams
        details["do_sample"] = False
        details["compute_dtype"] = "float32"

        def run(item):
            language = item_language(runtime, settings, item)
            with wave.open(item["audio"], "rb") as wav:
                if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (16000, 1, 2):
                    raise ValueError("Expected a canonical 16 kHz mono PCM16 WAV")
                if wav.getnframes() > 30 * 16000:
                    raise ValueError("Native Qwen3-ASR short-form reference accepts clips up to 30 seconds")
                samples = (
                    np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float32) / 32768
                )
            inputs = processor.apply_transcription_request(
                audio=samples, language=language, return_tensors="pt"
            ).to(device)
            with torch.inference_mode():
                tokens = model.generate(**inputs, max_new_tokens=settings["max_new_tokens"], do_sample=False)
            generated = tokens[:, inputs["input_ids"].shape[1] :]
            return processor.decode(generated, return_format="transcription_only")[0]

        return run, importlib.metadata.version("transformers"), device
    if runtime == "nemo-parakeet":
        import nemo.collections.asr as nemo_asr

        if settings["temperature"] != 0:
            raise ValueError("NeMo Parakeet adapter supports automatic language/greedy defaults only")
        checkpoints = list(Path(root).glob("*.nemo"))
        if len(checkpoints) != 1:
            raise ValueError("NeMo reference requires exactly one original .nemo checkpoint")
        model = nemo_asr.models.ASRModel.restore_from(str(checkpoints[0]))

        def run(item):
            item_language(runtime, settings, item)
            result = model.transcribe([item["audio"]], batch_size=1)
            item = result[0] if not isinstance(result, tuple) else result[0][0]
            return item if isinstance(item, str) else item.text

        return run, importlib.metadata.version("nemo_toolkit"), str(model.device)
    if runtime == "parakeet-transformers":
        import numpy as np
        import torch
        from transformers import AutoModelForTDT, AutoProcessor

        if settings["temperature"] != 0:
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

        def run(item):
            item_language(runtime, settings, item)
            with wave.open(item["audio"], "rb") as wav:
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

        model = load_model(root)

        def run(item):
            result = model.generate(
                item["audio"],
                max_tokens=settings["max_new_tokens"],
                language=item_language(runtime, settings, item),
                temperature=settings["temperature"],
                stream=False,
                verbose=False,
            )
            mx.synchronize()
            return result.text

        return run, importlib.metadata.version("mlx-audio"), "Apple Silicon / MLX"
    raise ValueError(f"No Python adapter for {runtime}")


def seed_everything(runtime: str, seed: int):
    import random

    random.seed(seed)
    if runtime == "mlx-audio-qwen":
        import mlx.core as mx

        mx.random.seed(seed)
    else:
        import torch

        torch.manual_seed(seed)


def engine_key(request: dict) -> str:
    """Requests with equal keys are served by the same loaded model."""
    return json.dumps(
        {"model": request["model"], "model_root": request["model_root"], "settings": request["settings"]},
        sort_keys=True,
    )


class Session:
    """One loaded model serving consecutive recordings. Only the first result pays, and reports, loading."""

    def __init__(self):
        self.loaded = None
        self.key = None
        self.served = 0

    def handle(self, request: dict) -> dict:
        runtime, settings = request["model"]["runtime"], request["settings"]
        seed = request.get("seed", 0)
        seed_everything(runtime, seed)
        if self.loaded is None:
            begin = time.perf_counter()
            details = {}
            run, version, device = transcriber(request, details)
            self.loaded, self.key = (run, version, device, details), engine_key(request)
            load_seconds, loading_condition = time.perf_counter() - begin, "new-process-os-cache-uncontrolled"
        elif engine_key(request) != self.key:
            raise ValueError("Request does not match the loaded model and settings")
        else:
            load_seconds, loading_condition = None, "reused-loaded-engine"
        run, version, device, details = self.loaded
        for _ in range(settings["warmups"]):
            run(request)
        seed_everything(runtime, seed)
        begin = time.perf_counter()
        text = run(request)
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
            "loading_condition": loading_condition,
            "engine_runs_before": self.served,
            "effective_settings": {
                **settings,
                "seed": seed,
                "whisper_segmentation": "sequential-long-form" if runtime == "whisper-transformers" else None,
                **details,
            },
            "streaming_mode": "batch",
            "energy_joules": None,
            "first_partial_seconds": None,
        }
        self.served += 1
        return result


def serve(lines):
    """Emit one STT_RESULT per request line. Any failure ends the process: a failed engine is never reused."""
    session = Session()
    for line in lines:
        if line.strip():
            result = session.handle(json.loads(line))
            print("STT_RESULT=" + json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)


def main():
    if sys.argv[1:] == ["--serve"]:
        serve(sys.stdin)
    else:
        serve([Path(sys.argv[1]).read_text()])


if __name__ == "__main__":
    main()
