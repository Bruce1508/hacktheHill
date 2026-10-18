from types import SimpleNamespace

import pytest

from backtrace.llm.providers import GeminiEmbeddingProvider, split_billable_units


def test_embed_batch_raises_if_response_count_does_not_match_input_count():
    provider = GeminiEmbeddingProvider("gemini-embed", "v1", dimension=3, api_key="fake-key")
    provider._client = SimpleNamespace(
        models=SimpleNamespace(embed_content=lambda **_: SimpleNamespace(embeddings=[SimpleNamespace(values=[0.1, 0.2, 0.3])], metadata=None))
    )
    with pytest.raises(RuntimeError, match="1 embeddings for 2 inputs"):
        provider.embed_batch(["first text", "second text"])


def test_embed_batch_falls_back_to_length_estimate_when_metadata_has_no_billable_count():
    provider = GeminiEmbeddingProvider("gemini-embed", "v1", dimension=3, api_key="fake-key")
    embeddings = [SimpleNamespace(values=[0.1, 0.2, 0.3]), SimpleNamespace(values=[0.4, 0.5, 0.6])]
    provider._client = SimpleNamespace(
        models=SimpleNamespace(
            embed_content=lambda **_: SimpleNamespace(embeddings=embeddings, metadata=SimpleNamespace(billable_character_count=None))
        )
    )
    results = provider.embed_batch(["first text", "second text longer"])
    assert [r.billable_units for r in results] == [len("first text"), len("second text longer")]


def test_split_billable_units_sums_to_total():
    texts = ["a", "bb", "ccc", "dddd"]
    parts = split_billable_units(100, texts)
    assert sum(parts) == 100


def test_split_billable_units_is_proportional():
    texts = ["a" * 10, "b" * 30]  # 1:3 length ratio
    parts = split_billable_units(40, texts)
    assert parts == [10, 30]


def test_split_billable_units_handles_a_single_item():
    parts = split_billable_units(57, ["only item"])
    assert parts == [57]


def test_split_billable_units_remainder_goes_on_the_last_item():
    texts = ["a", "a", "a"]  # equal lengths, total not evenly divisible by 3
    parts = split_billable_units(10, texts)
    assert sum(parts) == 10
    assert parts[0] == parts[1] == 3  # floor(10/3) each
    assert parts[2] == 4  # remainder
