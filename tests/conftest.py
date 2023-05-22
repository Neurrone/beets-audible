from unittest.mock import MagicMock

import pytest

from beetsplug.audible import Audible


@pytest.fixture(scope="session")
def mock_audible_plugin() -> MagicMock:
    out = MagicMock()
    out.sort_tracks = Audible.sort_tracks
    out.attempt_match_chapter_levenshtein = lambda x, y: Audible.attempt_match_chapter_levenshtein(out, x, y)
    out.attempt_match_natsort = lambda x, y: Audible.attempt_match_natsort(out, x, y)
    out.attempt_match_starting_numbers = lambda x, y: Audible.attempt_match_starting_numbers(out, x, y)
    out.attempt_match_trust_source_numbering = lambda x, y: Audible.attempt_match_trust_source_numbering(out, x, y)
    out.attempt_match_single_item = lambda x, y: Audible.attempt_match_single_item(out, x, y)
    out.config = {
        "fetch_art": True,
        "match_chapters": True,
        "source_weight": 0.0,
        "write_description_file": True,
        "trust_source_numbering": True,
        "write_reader_file": True,
        "include_narrator_in_artists": True,
        "goodreads_apikey": None,
    }
    return out
