import pytest
from stt_lab.runners import validate_parakeet_loading


def test_auxiliary_vad_exclusion_requires_explicit_condition_and_known_source():
    info = {"missing_keys": [], "unexpected_keys": ["vad_head.proj.weight", "vad_head.out.bias"]}
    with pytest.raises(ValueError):
        validate_parakeet_loading(info, {"repository": "moondream/parakeet-ultra"})
    model = {
        "repository": "moondream/parakeet-ultra",
        "reference_options": {"exclude_auxiliary_vad_head": True},
    }
    assert validate_parakeet_loading(info, model) == ["vad_head.out.bias", "vad_head.proj.weight"]
    with pytest.raises(ValueError):
        validate_parakeet_loading({**info, "missing_keys": ["encoder.weight"]}, model)
    with pytest.raises(ValueError):
        validate_parakeet_loading({**info, "unexpected_keys": ["unknown_decoder.weight"]}, model)
