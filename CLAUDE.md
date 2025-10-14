# CLAUDE.md

## Project Overview

This is a Beets plugin for audiobook management that fetches metadata from Audible/Audnex APIs and tags audiobook files appropriately for Plex, Audiobookshelf, or Booksonic.

## Development Setup

1. Install [uv](https://docs.astral.sh/uv/#getting-started)
2. Run Beets with the plugin from source: `uv run beet -v version` (verify `audible` appears in plugin list)
3. Note: Installing beets-copyartifacts3 in development breaks the ability to run from source

## Common Commands

### Testing

- Run tests: `pytest` or `uv run pytest`

### Code Quality

- Format code: `tox -e format` (runs black and isort)
  - Or directly: `black beetsplug tests` and `isort beetsplug tests`
- Lint code: `tox -e lint` (runs pylint)
  - Or directly: `pylint beetsplug/ tests/`
- Pre-commit hooks: `pre-commit run --all-files` (runs black and isort)

### Building

- Build package: `uv build` or `python -m build`

### Running Beets

- Run Beets commands during development: `uv run beet <command>`
- Example: `uv run beet import /path/to/audiobooks`

## Code Architecture

### Plugin Entry Point

The main plugin class is `Audible` in `beetsplug/audible.py`, which extends Beets' `MetadataSourcePlugin`. It:

- Registers event listeners for write operations and imports
- Adds custom media fields for audiobook-specific tags (album_sort, subtitle, series_name, series_position, etc.)
- Handles the metadata lookup workflow

### Metadata Source Priority

The plugin searches for book metadata in this order:

1. **metadata.yml** file in the book folder (for non-Audible content)
2. Album and artist tags from audio files
3. Folder name as fallback

### Core Components

**beetsplug/audible.py** - Main plugin logic

- `candidates()`: Searches for matching books and returns `AlbumInfo` objects
- `get_album_info()`: Fetches book details from Audnex API by ASIN
- `get_album_from_yaml_metadata()`: Parses metadata.yml for non-Audible content
- `fetch_art()`: Downloads cover art during import
- `on_write()`: Strips unwanted tags and handles m4b-specific tag writing
- `write_book_description_and_narrator()`: Writes desc.txt and reader.txt files

**beetsplug/api.py** - API interaction

- `search_audible()`: Searches Audible API by keywords
- `get_book_info()`: Fetches book and chapter data from Audnex
- `make_request()`: HTTP request wrapper with retry logic and rate limiting
- Supports multiple Audible regions (us, uk, ca, au, de, es, fr, in, it, jp)

**beetsplug/book.py** - Data models

- `Book`: Represents audiobook metadata (authors, narrators, series, genres, etc.)
- `BookChapters`: Chapter information with timestamps
- `from_audnex_book()`: Converts Audnex API responses to Book objects

**beetsplug/goodreads.py** - Optional Goodreads integration

- `get_original_date()`: Fetches original publication date from Goodreads

### Chapter Matching Logic

When `match_chapters: true` in config AND the number of files equals the number of chapters from Audible:

- Files are naturally sorted (to handle "chapter 1, 2, 10" correctly, not "1, 10, 2")
- Each file is matched to the corresponding chapter by index
- If chapter data is marked inaccurate or counts don't match, plugin creates dummy tracks using file metadata

### Region Handling

The plugin supports regional Audible metadata:

- Region can be set globally in config (`region: us`)
- Can be overridden per-book during import (press 'R' at import prompt)
- Region is automatically extracted from WOAF (album_url) tag if present
- Priority: book-level region > WOAF tag region > config region

### Tag Writing

Custom tags are defined using `mediafile.MediaField` with different storage styles for MP3/M4B/other formats. Key custom tags:

- `album_sort`: TSOA (MP3), soal (M4B) - Smart sorting with series support
- `series_name`: MVNM (MP3), ©mvn (M4B)
- `series_position`: MVIN (MP3), SERIES-PART (M4B)
- `subtitle`: TIT3 (MP3), custom M4B tag
- `album_url`: WOAF for MP3 disabled (see issue #71), custom M4B tag
- M4B-specific: `stik` (media type=2 for audiobook), `shwm` (show movement for series)

### Known Issues

1. MP3 WOAF tag temporarily disabled due to upstream bug (issue #71)
2. Moving files after import leaves desc.txt and reader.txt behind (Beets limitation)
3. The `mvi` tag for M4B only accepts integers, so series positions like "1-3" use alternate tag

## Code Style

- Line length: 120 characters (black/isort configured)
- Use black for formatting, isort for import sorting
- Match the existing style in the codebase
- Pre-commit hooks enforce formatting on commit
