# Repository Guidelines

## Project Overview

This plugin augments Beets with Audible/Audnex metadata so audiobook libraries import cleanly into Plex, Audiobookshelf, or Booksonic. It fetches book details, writes audiobook-specific tags, and drops helper files (cover art, `desc.txt`, `reader.txt`) during import.

## Project Structure & Module Organization

Core plugin code lives under `beetsplug/`. `audible.py` wires the plugin into Beets, `api.py` wraps Audible/Audnex lookups, `book.py` holds domain models, and `goodreads.py` gates the optional Goodreads enrichment. Tests reside in `tests/`, mirroring plugin modules; add new fixtures close to their consumers. Distribution assets land in `dist/` only after building, while `development.md` and `readme.md` document setup and usage—sync changes across them when behavior shifts.

## Development Setup

Install [uv](https://docs.astral.sh/uv/#getting-started) first, then install dependencies with `uv sync --locked --all-extras --dev`. Verify the plugin loads with `uv run beet -v version` (ensure `audible` shows up in the plugin list). Avoid installing `beets-copyartifacts3` in the same environment during development—it breaks running the plugin from source.

## Build, Test, and Development Commands

Use uv for reproducible environments: `uv run beet -v version` verifies the plugin loads in an isolated Beets session, and `uv run beet <command>` lets you execute arbitrary Beets commands while you work. Run tests with `uv run pytest` (or plain `pytest` once dependencies are installed). Run formatting and lint checks with Ruff: `uv run ruff format --check beetsplug tests` and `uv run ruff check beetsplug tests`. For local fixes, use `uv run ruff format` and `uv run ruff check --fix`. Build artifacts with `uv build` before publishing, and keep `uv.lock` aligned with dependency changes.

## Coding Style & Naming Conventions

Target Python >=3.9. Follow Ruff formatting and linting defaults configured in `pyproject.toml` (including 120-char lines and import sorting). Prefer descriptive snake_case for functions and module-level constants in SHOUT_CASE; classes follow CapWords. Keep side effects near Beets hooks and isolate network or file IO in helper modules. Add concise docstrings for any public helper or integration boundary.

## Architecture & Behaviors

- `beetsplug/audible.py` hosts the `Audible` plugin class. It registers write/import listeners, defines audiobook media fields, surfaces `candidates()` for searches, fetches metadata via `get_album_info()`, falls back to `get_album_from_yaml_metadata()` for non-Audible material, downloads art, and writes `desc.txt`/`reader.txt` on import.
- `beetsplug/api.py` wraps Audible/Audnex HTTP calls (`search_audible()`, `get_book_info()`, `make_request()`) with retry logic and multi-region (us/uk/ca/au/de/es/fr/in/it/jp) support. `beetsplug/book.py` holds the data models (`Book`, `BookChapters`, `from_audnex_book()`). `beetsplug/goodreads.py` optionally enriches original publication dates.
- Metadata sources are consulted in order: `metadata.yml` in the folder, then embedded album/artist tags, then folder name as a last resort.
- Chapter matching keeps Audible chapter data when `match_chapters: true` and the track count equals Audible’s chapter count. Otherwise, tracks are rebuilt from naturally sorted local files to match import items; chapter inaccuracy is currently warned about.
- Region precedence: per-book override during import (`r` prompt) beats WOAF-derived region, which beats the global config value.
- Custom tags rely on `mediafile.MediaField` with per-format mapping (MP3 TSOA/MVNM/MVIN/TIT3, M4B soal/©mvn/SERIES-PART/custom subtitle tags, `stik`, `shwm`, WOAF via custom freeform tag). WOAF writes are disabled for MP3 until issue #71 is resolved.

## Testing Guidelines

Pytest is the primary framework. Name tests `test_<behavior>()` inside modules that mirror the code under test. Before submitting, run `uv run pytest`, `uv run ruff format --check beetsplug tests`, and `uv run ruff check beetsplug tests`. When adding API integrations, stub external calls and cover both success and error paths; regression tests should assert Beets emits the expected fields (author, narrator, paths).

## Commit & Pull Request Guidelines

Recent history uses conventional prefixes (`fix:`, `doc:`, etc.) plus an imperative summary (“fix compatibility with Beets 2.5.0”). Reference related issues in the body, and keep commits scoped to one change. Pull requests should describe motivation, outline testing (commands run), and include sample configs when behavior or docs change. Ensure changelog entries accompany user-facing tweaks.

## Known Issues & Limitations

- MP3 WOAF tag writes remain disabled (issue #71) until the upstream bug is fixed.
- Moving imported files leaves `desc.txt` and `reader.txt` behind because Beets doesn’t move auxiliary artifacts.
- The `mvi` tag for M4B accepts integers only, so complex series positions (for example, `1-3`) rely on alternate tags.

## Security & Configuration Tips

Never commit personal Audible credentials or Goodreads API keys; read them via env vars or local config files ignored by git. Sanitise `metadata.yml` samples before sharing—they often contain proprietary descriptions. Double-check that generated `desc.txt` or `reader.txt` artifacts stay out of commits unless explicitly needed for documentation.
