from stt_lab.runners import WHISPER_MAX_PREFIX_TOKENS, whisper_max_new_tokens


def test_whisper_budget_leaves_room_for_prefix_tokens():
    # The experiment default is 1024; prefix tokens (start, language, task, no-timestamps) share the 448 positions.
    budget = whisper_max_new_tokens(1024, 448)
    assert budget == 448 - WHISPER_MAX_PREFIX_TOKENS
    assert budget + WHISPER_MAX_PREFIX_TOKENS <= 448


def test_whisper_budget_keeps_smaller_requests():
    assert whisper_max_new_tokens(32, 448) == 32
