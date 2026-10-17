from backtrace.llm.providers import split_billable_units


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
