import pytest
from stt_lab.evaluation import aggregate, distribution, normalize, paired_penalty, score


def test_edit_counts_and_alignment():
    result = score("the red cat sat", "the blue cat sits now", "en")
    assert result["normalized"]["word"] == {
        "substitutions": 2,
        "deletions": 0,
        "insertions": 1,
        "reference_length": 4,
        "rate": 0.75,
    }
    assert any(x["kind"] == "insert" for x in result["alignment"])


def test_unicode_preserves_lexical_distinctions():
    assert normalize("I İ ISPARTA İZMİR", "tr") == "ı i ısparta izmir"
    assert normalize("I İ", "mixed") == "i i\u0307"
    assert normalize("أمل امل عَلَم علم", "ar") == "أمل امل عَلَم علم"
    assert normalize("cafe\u0301,\tTEST!", "en") == "café test"
    assert score("İZMİR", "izmir", "tr")["normalized"]["word"]["rate"] == 0
    assert score("أمل", "امل", "ar")["normalized"]["character"]["rate"] > 0


def test_strict_metrics_and_empty_reference():
    result = score("Hello!", "hello", "en")
    assert result["strict"]["word"]["rate"] == 1
    assert result["normalized"]["word"]["rate"] == 0
    empty = score("", "hallucination", "en")["normalized"]["word"]
    assert empty["rate"] is None
    assert empty["insertions"] == 1
    assert score("abc", "", "en")["normalized"]["word"]["deletions"] == 1


def test_corpus_uses_counts_instead_of_mean_percentages():
    rows = [score("a", "b", "en"), score("one two three four", "one two three four", "en")]
    assert aggregate(rows)["word"]["rate"] == 0.2
    assert aggregate([])["word"]["rate"] is None


def test_grapheme_cer_and_distributions():
    assert score("أ", "ا", "ar")["normalized"]["character"]["reference_length"] == 1
    assert distribution([1, 2, 3, 4])["median"] == 2.5
    assert distribution([])["p95"] is None
    with pytest.raises(ValueError):
        distribution([float("nan")])


def test_paired_penalty_uses_same_recordings():
    reference = {"a": score("one two", "one two", "en"), "b": score("three", "four", "en")}
    deployment = {"a": score("one two", "one", "en")}
    result = paired_penalty(reference, deployment, seed=1)
    assert result["paired_recordings"] == 1
    assert result["penalty"] == 0.5
