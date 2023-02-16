from unittest.mock import MagicMock

import pytest


@pytest.fixture(scope="session")
def mock_audible_plugin() -> MagicMock:
    out = MagicMock()
    out.config = {
        "fetch_art": True,
        "match_chapters": True,
        "source_weight": 0.0,
        "write_description_file": True,
        "write_reader_file": True,
        "include_narrator_in_artists": True,
        "goodreads_apikey": None,
    }
    return out
