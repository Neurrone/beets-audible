from copy import deepcopy
from pathlib import Path
from random import shuffle
from typing import List, Optional, Sequence, Tuple
from unittest.mock import MagicMock

import pytest
from beets.library import Item
from beets.util import bytestring_path

import beetsplug.audible as audible


def create_mock_item(item_name: str, item_index: int, filename: Optional[str] = None) -> MagicMock:
    out = MagicMock()
    out.title = item_name
    out.track = item_index
    out.path = bytestring_path(str(Path(".", "test_audiobook", filename if filename else item_name + ".mp3").resolve()))
    out.__str__.return_value = f"{item_name} {out.path}"
    return out


def randomise_lists(lists: Tuple[List, ...], n: int = 5) -> Sequence[Tuple[List, List]]:
    out = []
    for l in lists:
        for i in range(1, n):
            copy = deepcopy(l)
            shuffle(copy)
            out.append((l, copy))
    return out


chapter_lists = (
    [
        create_mock_item("01", 0),
        create_mock_item("02", 0),
        create_mock_item("03", 0),
        create_mock_item("04", 0),
        create_mock_item("05", 0),
        create_mock_item("06", 0),
        create_mock_item("07", 0),
        create_mock_item("08", 0),
        create_mock_item("09", 0),
        create_mock_item("10", 0),
        create_mock_item("11", 0),
        create_mock_item("12", 0),
        create_mock_item("13", 0),
    ],
    [
        create_mock_item("Chapter 1", 0),
        create_mock_item("Chapter 2", 0),
        create_mock_item("Chapter 3", 0),
        create_mock_item("Chapter 4", 0),
        create_mock_item("Chapter 5", 0),
        create_mock_item("Chapter 6", 0),
        create_mock_item("Chapter 7", 0),
        create_mock_item("Chapter 8", 0),
        create_mock_item("Chapter 9", 0),
        create_mock_item("Chapter 10", 0),
    ],
    [
        create_mock_item("Chapter 01", 0),
        create_mock_item("Chapter 02", 0),
        create_mock_item("Chapter 03", 0),
        create_mock_item("Chapter 04", 0),
        create_mock_item("Chapter 05", 0),
        create_mock_item("Chapter 06", 0),
        create_mock_item("Chapter 07", 0),
        create_mock_item("Chapter 08", 0),
        create_mock_item("Chapter 09", 0),
        create_mock_item("Chapter 10", 0),
    ],
    [
        create_mock_item("Chapter - 01", 0),
        create_mock_item("Chapter - 02", 0),
        create_mock_item("Chapter - 03", 0),
        create_mock_item("Chapter - 04", 0),
        create_mock_item("Chapter - 05", 0),
        create_mock_item("Chapter - 06", 0),
        create_mock_item("Chapter - 07", 0),
        create_mock_item("Chapter - 08", 0),
        create_mock_item("Chapter - 09", 0),
        create_mock_item("Chapter - 10", 0),
        create_mock_item("Chapter - 11", 0),
        create_mock_item("Chapter - 12", 0),
        create_mock_item("Chapter - 13", 0),
    ],
    [
        create_mock_item("Chapter-01", 0),
        create_mock_item("Chapter-02", 0),
        create_mock_item("Chapter-03", 0),
        create_mock_item("Chapter-04", 0),
        create_mock_item("Chapter-05", 0),
        create_mock_item("Chapter-06", 0),
        create_mock_item("Chapter-07", 0),
        create_mock_item("Chapter-08", 0),
        create_mock_item("Chapter-09", 0),
        create_mock_item("Chapter-10", 0),
        create_mock_item("Chapter-11", 0),
        create_mock_item("Chapter-12", 0),
        create_mock_item("Chapter-13", 0),
    ],
    [
        create_mock_item("Mediocre-Part01", 0),
        create_mock_item("Mediocre-Part02", 0),
        create_mock_item("Mediocre-Part03", 0),
        create_mock_item("Mediocre-Part04", 0),
        create_mock_item("Mediocre-Part05", 0),
        create_mock_item("Mediocre-Part06", 0),
        create_mock_item("Mediocre-Part07", 0),
        create_mock_item("Mediocre-Part08", 0),
        create_mock_item("Mediocre-Part09", 0),
        create_mock_item("Mediocre-Part10", 0),
        create_mock_item("Mediocre-Part11", 0),
        create_mock_item("Mediocre-Part12", 0),
    ],
    [
        create_mock_item("Chapter 1 The DC Sniper The Untold Story of the DC Sniper Investigation - 1.m4b", 0),
        create_mock_item("Chapter 2 Terrorism The Untold Story of the DC Sniper Investigation - 1.m4b", 0),
        create_mock_item("Chapter 3 Brothers in the Arena The Untold Story of the DC Sniper Investigation - 1.m4b", 0),
        create_mock_item("Chapter 4 Call Me God The Untold Story of the DC Sniper Investigation - 1.m4b", 0),
        create_mock_item("Chapter 5 Close to Home The Untold Story of the DC Sniper Investigation - 1.m4b", 0),
        create_mock_item("Chapter 6 A Local Case The Untold Story of the DC Sniper Investigation - 1.m4b", 0),
        create_mock_item("Chapter 7 Demands The Untold Story of the DC Sniper Investigation - 1.m4b", 0),
        create_mock_item("Chapter 8 The Profile The Untold Story of the DC Sniper Investigation - 1.m4b", 0),
        create_mock_item("Chapter 9 Suspects The Untold Story of the DC Sniper Investigation - 1.m4b", 0),
        create_mock_item("Chapter 10 Prelude The Untold Story of the DC Sniper Investigation - 1.m4b", 0),
        create_mock_item("Chapter 11 The Arrest The Untold Story of the DC Sniper Investigation - 1.m4b", 0),
        create_mock_item("Chapter 12 Revenge The Untold Story of the DC Sniper Investigation - 1.m4b", 0),
        create_mock_item(
            "Chapter 13 The Trials of a Teenager The Untold Story of the DC Sniper Investigation - 1.m4b", 0
        ),
        create_mock_item("Chapter 14 Last Words The Untold Story of the DC Sniper Investigation - 1.m4b", 0),
    ],
    [
        create_mock_item("Prologue", 0),
        create_mock_item("Chapter 1", 0),
        create_mock_item("Chapter 2", 0),
        create_mock_item("Chapter 3", 0),
        create_mock_item("Chapter 4", 0),
        create_mock_item("Chapter 5", 0),
        create_mock_item("Chapter 6", 0),
        create_mock_item("Chapter 7", 0),
        create_mock_item("Chapter 8", 0),
        create_mock_item("Chapter 9", 0),
        create_mock_item("Chapter 10", 0),
        create_mock_item("End", 0),
        create_mock_item("Author's Note", 0),
    ],
)


@pytest.mark.parametrize("items", chapter_lists)
def test_sort_items(items: List[Item]):
    expected = deepcopy(items)
    result = audible.sort_items(items)
    assert all([str(result[i]) == str(e) for i, e in enumerate(expected)])


@pytest.mark.parametrize("items", chapter_lists)
def test_sort_items_reversed(items: List[Item]):
    expected = deepcopy(items)
    result = audible.sort_items(reversed(items))
    assert all([str(result[i]) == str(e) for i, e in enumerate(expected)])


@pytest.mark.parametrize("correct, items", randomise_lists(chapter_lists, 10))
def test_sort_items_randomised(correct: List[Item], items: List[Item]):
    result = audible.sort_items(items)
    assert all([str(result[i]) == str(e) for i, e in enumerate(correct)])


@pytest.mark.parametrize(
    ("test_token1", "test_token2", "expected"),
    (
        ("example", "example", 0),
        ("exampl", "example", 1),
        ("example1", "example", 10),
        ("example1", "example2", 10),
        ("example1", "example12", 10),
        ("example21", "example12", 20),
        ("example1", "example1 test", 5),
    ),
)
def test_specialised_levenshtein(test_token1: str, test_token2: str, expected: int):
    result = audible.specialised_levenshtein(test_token1, test_token2)
    assert isinstance(result, int)
    assert result == expected


@pytest.mark.parametrize(
    ("test_tokens", "expected_prefix", "expected_suffix"),
    (
        ([], "", ""),
        (
            [
                "test",
            ],
            "",
            "",
        ),
        (["test", "test"], "test", "test"),
        (["test1", "test2"], "test", ""),
        (["testing", "test2"], "test", ""),
        (["testing", "test2"], "test", ""),
        (["prefix1suffix", "prefix2suffix"], "prefix", "suffix"),
    ),
)
def test_find_regular_affixes(test_tokens: List[str], expected_prefix: str, expected_suffix: str):
    results = audible.find_regular_affixes(test_tokens)
    assert results[0] == expected_prefix
    assert results[1] == expected_suffix


@pytest.mark.parametrize(
    ("test_token", "test_affixes", "expected"),
    (
        ("example", ("", ""), "example"),
        ("test", ("test", ""), ""),
        ("test", ("", "test"), ""),
        ('testexampletest',('test',''), 'exampletest'),
        ('testexampletest', ('','test'), 'testexample'),
        ('test.mp3', ('','.mp3'), 'test'),
        ('testxmp3',('','.mp3'), 'testxmp3'),
    ),
)
def test_strip_affixes(test_token: str, test_affixes: Tuple[str, str], expected: str):
    result = audible.strip_affixes(test_token, test_affixes)
    assert result == expected
