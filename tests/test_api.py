from typing import Dict, Tuple
from xml.etree.ElementTree import Element

import pytest

import beetsplug.api as api


@pytest.mark.parametrize(
    ("test_asin", "expected_dicts", "expected_chapters"),
    (
        (
            "1529353823",
            (
                {
                    "asin": "1529353823",
                    "formatType": "unabridged",
                    "language": "english",
                },
                {
                    "brandIntroDurationMs": 1625,
                },
            ),
            12,
        ),
    ),
)
def test_call_audnex_for_book_info(test_asin: str, expected_dicts: Tuple[Dict, Dict], expected_chapters: int):
    result = api.call_audnex_for_book_info(test_asin)
    assert expected_chapters == len(result[1]["chapters"])
    assert all([expected_dicts[0].get(k) == result[0][k] for k in expected_dicts[0].keys()])
    assert all([expected_dicts[1].get(k) == result[1][k] for k in expected_dicts[1].keys()])


@pytest.mark.parametrize(
    "test_asin",
    (
        "1529353823",
        "1529063094",
    ),
)
def test_get_book_info(test_asin: str):
    # Just checking to make sure that there are no exceptions thrown
    _, _ = api.get_book_info(test_asin)
