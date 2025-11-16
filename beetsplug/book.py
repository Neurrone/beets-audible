import re
from typing import Optional

from markdownify import markdownify as md

# This would be much less verbose with dataclasses, only available in Python 3.7+
# Beets has a minimum Python version requirement of 3.6, hence I'm not using dataclasses here


class Author:
    asin: Optional[str]
    name: str

    def __init__(self, asin, name):
        self.asin = asin
        self.name = name


class Genre:
    asin: str
    name: str

    def __init__(self, asin, name):
        self.asin = asin
        self.name = name


class Tag:
    """
    Tags associated with the book, e.g "Action & Adventure", "Epic"
    """

    asin: str
    name: str

    def __init__(self, asin, name):
        self.asin = asin
        self.name = name


class Narrator:
    name: str

    def __init__(self, name):
        self.name = name


class Series:
    asin: str
    name: str
    # Yes, sadly its possible for series to not have a position
    position: Optional[str]  # e.g, "2", "8.5", "1-5"

    def __init__(self, asin, name, position):
        self.asin = asin
        self.name = name
        self.position = position


class Book:
    asin: str
    authors: list[Author]
    description: str
    format_type: str  # e.g, "unabridged"
    genres: list[Genre]  # may be an empty list
    image_url: str
    language: str
    narrators: list[Narrator]
    publisher: str
    release_date: str  # yyyy-mm-dd format
    runtime_length_min: int
    series: Optional[Series]
    subtitle: Optional[str]
    summary_html: str
    summary_markdown: str
    tags: list[Tag]  # may be an empty list
    title: str
    region: Optional[str]

    def __init__(
        self,
        asin,
        authors,
        description,
        format_type,
        genres,
        image_url,
        language,
        narrators,
        publisher,
        release_date,
        runtime_length_min,
        series,
        subtitle,
        summary_html,
        summary_markdown,
        tags,
        title,
        region,
    ):
        self.asin = asin
        self.authors = authors
        self.description = description
        self.format_type = format_type
        self.genres = genres
        self.image_url = image_url
        self.language = language.capitalize()
        self.narrators = narrators
        self.publisher = publisher
        self.release_date = release_date
        self.runtime_length_min = runtime_length_min
        self.series = series
        self.subtitle = subtitle
        self.summary_html = summary_html
        self.summary_markdown = summary_markdown
        self.tags = tags
        self.title = title
        self.region = region

    @staticmethod
    def from_audnex_book(b: dict):
        """
        Creates a `Book` from an Audnex book result
        """
        series_primary = b.get("seriesPrimary")
        if series_primary:
            pos = series_primary.get("position")
            if pos:
                match = re.search(r"[\d.\-]+", pos)
                series_position = match.group(0) if match else None
            else:
                series_position = None
            series = Series(asin=series_primary["asin"], name=series_primary["name"], position=series_position)
        else:
            series = None
        summary_html = b["summary"]
        summary_markdown = md(summary_html)
        # Remove blank lines from the start and end, as well as whitespace from each line
        normalized_summary_markdown = "\n".join([line.strip() for line in summary_markdown.strip().splitlines()])
        return Book(
            asin=b["asin"],
            authors=[Author(asin=a.get("asin"), name=a["name"]) for a in b["authors"]],
            description=b["description"],
            format_type=b["formatType"],
            genres=[
                # API response may not contain genre info
                Genre(asin=g["asin"], name=g["name"])
                for g in b.get("genres", [])
                if g["type"] == "genre"
            ],
            image_url=b["image"],
            language=b["language"],
            narrators=[Narrator(name=n["name"]) for n in b["narrators"]],
            publisher=b["publisherName"],
            release_date=b["releaseDate"][:10],  # ignore timestamp from iso8601 string
            runtime_length_min=b["runtimeLengthMin"],
            series=series,
            subtitle=b.get("subtitle"),
            summary_html=summary_html,
            summary_markdown=normalized_summary_markdown,
            tags=[
                # API response may not contain tag info
                Tag(asin=g["asin"], name=g["name"])
                for g in b.get("genres", [])
                if g["type"] == "tag"
            ],
            title=b["title"],
            region=b["region"],
        )


class Chapter:
    length_ms: int
    start_offset_ms: int
    start_offset_sec: int
    title: str

    def __init__(self, length_ms, start_offset_ms, start_offset_sec, title):
        self.length_ms = length_ms
        self.start_offset_ms = start_offset_ms
        self.start_offset_sec = start_offset_sec
        self.title = title


class BookChapters:
    asin: str
    bran_intro_duration_ms: int
    brand_outro_duration_ms: int
    chapters: list[Chapter]
    is_accurate: bool
    runtime_length_ms: int
    runtime_length_sec: int

    def __init__(
        self,
        asin,
        bran_intro_duration_ms,
        brand_outro_duration_ms,
        chapters,
        is_accurate,
        runtime_length_ms,
        runtime_length_sec,
    ):
        self.asin = asin
        self.bran_intro_duration_ms = bran_intro_duration_ms
        self.brand_outro_duration_ms = brand_outro_duration_ms
        self.chapters = chapters
        self.is_accurate = is_accurate
        self.runtime_length_ms = runtime_length_ms
        self.runtime_length_sec = runtime_length_sec

    @staticmethod
    def from_audnex_chapter_info(c: dict):
        """
        Creates a `BookChapters` instance from audnex's /book/{asin}/chapters endpoint
        """
        return BookChapters(
            asin=c["asin"],
            bran_intro_duration_ms=c["brandIntroDurationMs"],
            brand_outro_duration_ms=c["brandOutroDurationMs"],
            chapters=[
                Chapter(
                    length_ms=c["lengthMs"],
                    start_offset_ms=c["startOffsetMs"],
                    start_offset_sec=c["startOffsetSec"],
                    title=c["title"],
                )
                for c in c["chapters"]
            ],
            is_accurate=c["isAccurate"],
            runtime_length_ms=c["runtimeLengthMs"],
            runtime_length_sec=c["runtimeLengthSec"],
        )
