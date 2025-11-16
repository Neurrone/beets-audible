import datetime
import os
import pathlib
import re
import urllib.error
from contextlib import suppress
from tempfile import NamedTemporaryFile

import mediafile
import yaml
from beets import importer, ui, util
from beets.autotag.hooks import AlbumInfo, TrackInfo
from beets.metadata_plugins import MetadataSourcePlugin
from beets.ui.commands import PromptChoice
from natsort import os_sorted

from .api import (
    AUDIBLE_REGIONS,
    get_audible_album_region,
    get_audible_album_url,
    get_book_info,
    make_request,
    search_audible,
)
from .goodreads import get_original_date


class Audible(MetadataSourcePlugin):
    data_source = "Audible"

    def __init__(self):
        super().__init__()

        self.config.add(
            {
                "fetch_art": True,
                "match_chapters": True,
                "data_source_mismatch_penalty": 0.0,
                "write_description_file": True,
                "write_reader_file": True,
                "include_narrator_in_artists": True,
                "keep_series_reference_in_title": True,
                "keep_series_reference_in_subtitle": True,
                "goodreads_apikey": None,
                "region": "us",
            }
        )
        self.config["goodreads_apikey"].redact = True
        # Check that a 'region' value in the config is one of the provided choices
        self.config["region"].as_choice(AUDIBLE_REGIONS)
        # Mapping of asin to cover art urls
        self.cover_art_urls = {}
        # stores paths of downloaded cover art to be used during import
        self.cover_art = {}

        self.register_listener("write", self.on_write)
        self.register_listener("import_task_files", self.on_import_task_files)
        self.register_listener("import_task_created", self.on_import_task_created)
        self.register_listener("before_choose_candidate", self.before_choose_candidate_event)

        if self.config["fetch_art"]:
            self.import_stages = [self.fetch_art]

        # see the following:
        # Beet's internal mapping to tags: https://github.com/beetbox/mediafile/blob/master/mediafile.py
        # Mp3tag's mapping: https://docs.mp3tag.de/mapping/
        # Tag Mapping from the Hydrogenaudio Knowledgebase: https://wiki.hydrogenaud.io/index.php?title=Tag_Mapping
        # List of M4b tags: https://mutagen.readthedocs.io/en/latest/api/mp4.html
        album_sort = mediafile.MediaField(
            mediafile.MP3StorageStyle("TSOA"),
            mediafile.MP4StorageStyle("soal"),
            mediafile.StorageStyle("TSOA"),
            mediafile.ASFStorageStyle("WM/AlbumSortOrder"),
        )
        self.add_media_field("album_sort", album_sort)
        desc = mediafile.MediaField(mediafile.MP4StorageStyle("desc"))
        self.add_media_field("desc", desc)
        itunes_media_type = mediafile.MediaField(
            mediafile.MP4StorageStyle("stik", as_type=int),
        )
        self.add_media_field("itunes_media_type", itunes_media_type)
        show_movement = mediafile.MediaField(
            mediafile.MP4StorageStyle("shwm", as_type=int),
        )
        self.add_media_field("show_movement", show_movement)

        series_name = mediafile.MediaField(
            mediafile.MP3StorageStyle("MVNM"),
            mediafile.MP3DescStorageStyle("SERIES"),
            mediafile.MP4StorageStyle("\xa9mvn"),
            mediafile.MP4StorageStyle("----:com.apple.iTunes:SERIES"),
            mediafile.StorageStyle("MVNM"),
        )
        self.add_media_field("series_name", series_name)
        series_position = mediafile.MediaField(
            mediafile.MP3StorageStyle("MVIN"),
            mediafile.MP3DescStorageStyle("SERIES-PART"),
            # Using the "mvi" tag for M4b wouldn't work when the value can't be converted to an integer
            # For instance, an m4b containing multiple books has series position "1-3"
            # Trying to do so would cause an exception, hence why this is commented out here
            # and handled below separately
            # mediafile.MP4StorageStyle('\xa9mvi'),
            mediafile.MP4StorageStyle("----:com.apple.iTunes:SERIES-PART"),
            mediafile.StorageStyle("MVIN"),
        )
        self.add_media_field("series_position", series_position)
        mvi = mediafile.MediaField(
            mediafile.MP4StorageStyle("\xa9mvi", as_type=int),
        )
        self.add_media_field("mvi", mvi)

        subtitle = mediafile.MediaField(
            mediafile.MP3StorageStyle("TIT3"),
            mediafile.MP4StorageStyle("----:com.apple.iTunes:SUBTITLE"),
            mediafile.StorageStyle("TIT3"),
            mediafile.ASFStorageStyle("WM/SubTitle"),
        )
        self.add_media_field("subtitle", subtitle)

        album_url = mediafile.MediaField(
            # disable reading / writing of WOAF for mp3, see https://github.com/Neurrone/beets-audible/issues/71
            # mediafile.MP3StorageStyle("WOAF"),
            mediafile.MP4StorageStyle("----:com.apple.iTunes:WWWAUDIOFILE"),
            mediafile.StorageStyle("WOAF"),
            mediafile.ASFStorageStyle("WM/AudioFileURL"),
        )
        self.add_media_field("album_url", album_url)

        region = mediafile.MediaField()
        self.add_media_field("region", region)

        self._recent_items = []

    def candidates(self, items, artist, album, va_likely):
        """Returns a list of AlbumInfo objects for Audible search results
        matching an album and artist (if not various).
        """
        self._recent_items = list(items)
        folder_path = pathlib.Path(items[0].path.decode()).parent
        yml_metadata_file_path = folder_path / "metadata.yml"
        if yml_metadata_file_path.is_file():
            self._log.debug("Reading data from metadata.yml")
            try:
                with open(str(yml_metadata_file_path)) as f:
                    data = yaml.load(f, Loader=yaml.SafeLoader)
                    return [self.get_album_from_yaml_metadata(data, items)]
            except Exception:
                self._log.error("Error while reading data from metadata.yml", exc_info=True)
                return []

        if not album and not artist:
            folder_name = folder_path.name
            self._log.warn(f"Files missing album and artist tags. Attempting query based on folder name {folder_name}")
            query = folder_name
        else:
            query = album if va_likely else f"{album} {artist}"

        # Strip medium information from query, Things like "CD1" and "disk 1"
        # can also negate an otherwise positive result.
        query = re.sub(r"(?i)\b(CD|disc)\s*\d+", "", query)
        # Strip "(unabridged)" or "(abridged)"
        abridged_indicator = r"(?i)\((unabridged|abridged)\)"
        query = re.sub(abridged_indicator, "", query)

        # The book level region has a higher priority than the config level.
        region = get_item_region(items[0])
        if region is None:
            region = self.config["region"].get()

        self._log.debug(f"Searching Audible for {query} in the '{region}' region")
        albums = self.get_albums(query, region)
        for a in albums:
            is_chapter_data_accurate = a.is_chapter_data_accurate
            punctuation = r"[^\w\s\d]"
            # normalize by removing punctuation, converting to lowercase,
            # as well as changing multiple consecutive spaces in the string to a single space
            normalized_book_title = re.sub(punctuation, "", a.album.strip().lower())
            normalized_book_title = " ".join(normalized_book_title.split())
            normalized_album_name = re.sub(abridged_indicator, "", album.strip().lower())
            normalized_album_name = re.sub(punctuation, "", normalized_album_name)

            normalized_album_name = " ".join(normalized_album_name.split())
            self._log.debug(f"Matching album name {normalized_album_name} with book title {normalized_book_title}")
            # account for different length strings
            is_likely_match = (
                normalized_album_name in normalized_book_title or normalized_book_title in normalized_album_name
            )
            is_chapterized = len(a.tracks) == len(items)
            # matching doesn't work well if the number of files in the album doesn't match the number of chapters
            # As a workaround, return the same number of tracks as the number of files.
            # This white lie is a workaround but works extraordinarily well
            if self.config["match_chapters"] and is_likely_match and is_chapterized and not is_chapter_data_accurate:
                # Logging this for now because this situation
                # is technically possible (based on the API) but unsure how often it happens
                self._log.warn(f"Chapter data for {a.album} could be inaccurate.")

            chapter_count_from_audible = self.maybe_align_tracks_with_items(a, items, is_likely_match=is_likely_match)
            if chapter_count_from_audible is not None:
                self._log.debug(
                    f"Attempting to match book: album {album} with {len(items)} files"
                    f" to book {a.album} with {chapter_count_from_audible} chapters."
                )
        return albums

    def maybe_align_tracks_with_items(self, album_info, items, *, is_likely_match=True):
        """Override chapter data from Audible with the current file list when needed."""
        if not is_likely_match or not items or not album_info.tracks:
            return None

        is_chapterized = len(album_info.tracks) == len(items)
        if self.config["match_chapters"] and is_chapterized:
            return None

        chapter_count_from_audible = len(album_info.tracks)

        common_track_attributes = dict(album_info.tracks[0])
        del common_track_attributes["index"]
        del common_track_attributes["length"]
        del common_track_attributes["title"]

        # Ignore existing track numbers, and instead sort based on file path
        # Use natural sorting instead of lexigraphical to avoid this order:
        # chapter 1, 10, 12, ..., 19, 2, etc
        # This does work correctly when the album has multiple disks
        # using the bytestring_path function from Beets is needed for correctness
        # I was noticing inaccurate sorting if using str to convert paths to strings
        naturally_sorted_items = os_sorted(items, key=lambda i: util.bytestring_path(i.path))
        album_info.tracks = [
            TrackInfo(**common_track_attributes, title=item.title, length=item.length, index=i + 1)
            for i, item in enumerate(naturally_sorted_items)
        ]
        return chapter_count_from_audible

    def get_album_from_yaml_metadata(self, data, items):
        """Returns an `AlbumInfo` object by populating it with details from metadata.yml"""
        title = data["title"]
        subtitle = data.get("subtitle")
        release_date = data["releaseDate"]
        series_name = data.get("series")
        series_position = data.get("seriesPosition")
        content_group_description = None
        if series_name:
            if series_position:
                album_sort = f"{series_name} {series_position} - {title}"
                content_group_description = f"{series_name}, Book #{series_position}"
            else:
                album_sort = f"{series_name} - {title}"
        elif subtitle:
            album_sort = f"{title} - {subtitle}"
        else:
            album_sort = title

        authors = ", ".join(data["authors"])
        narrators = ", ".join(data["narrators"])
        authors_and_narrators = ", ".join([authors, narrators])
        artists = authors_and_narrators if self.config["include_narrator_in_artists"] else authors

        description = data["description"]
        genres = "/".join(data["genres"])

        common_attributes = {
            "artist_id": None,
            "album_sort": album_sort,
            "composer": narrators,
            "grouping": content_group_description,
            "genre": genres,
            "series_name": series_name,
            "series_position": series_position,
            "comments": description,
            "data_source": "YAML",
            "subtitle": subtitle,
            "album_url": None,
            "region": None,
        }

        naturally_sorted_items = os_sorted(items, key=lambda i: util.bytestring_path(i.path))
        # populate tracks by using some of the info from the files being imported
        tracks = [
            TrackInfo(
                **common_attributes,
                track_id=None,
                artist=artists,
                index=i + 1,
                length=item.length,
                title=item.title,
                medium=1,
            )
            for i, item in enumerate(naturally_sorted_items)
        ]

        year = release_date.year
        month = release_date.month
        day = release_date.day
        language = data.get("language", "English")
        publisher = data["publisher"]

        return AlbumInfo(
            tracks=tracks,
            album=title,
            album_id=None,
            albumtype="audiobook",
            mediums=1,
            artist=authors,
            year=year,
            month=month,
            day=day,
            original_year=year,
            original_month=month,
            original_day=day,
            language=language,
            label=publisher,
            **common_attributes,
        )

    def album_for_id(self, album_id):
        """
        Fetches book info by its asin and returns an AlbumInfo object
        or None if the book was not found.
        """
        asin = album_id
        self._log.debug(f"Searching for book {asin}")
        try:
            info = self.get_album_info(asin, self.config["region"].get())
            recent_items = self._recent_items
            if recent_items:
                aligned = self.maybe_align_tracks_with_items(info, recent_items)
                if aligned is not None:
                    self._log.debug(
                        "Matched ASIN %s with local files (%s chapters -> %s files)",
                        asin,
                        aligned,
                        len(recent_items),
                    )
            return info
        except Exception:
            # TODO: handle errors properly and distinguish between general errors and 404s
            self._log.debug(f"Exception while getting book {asin}", exc_info=True)
            return None

    def get_albums(self, query, region):
        """Returns a list of AlbumInfo objects for an Audible search query."""

        try:
            results = search_audible(query, region)
        except Exception:
            self._log.warn("Could not connect to Audible API while searching for {0!r}", query, exc_info=True)
            return []

        try:
            products = results["products"]
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            products_without_unreleased_entries = [p for p in products if p["release_date"] <= today]
            if len(products_without_unreleased_entries) < len(products):
                # see https://github.com/laxamentumtech/audnexus/issues/239
                self._log.info(
                    f"Excluded {len(products) - len(products_without_unreleased_entries)} books which have"
                    f" not been released from consideration."
                )
            out = []
            for p in products_without_unreleased_entries:
                try:
                    out.append(self.get_album_info(p["asin"], region))
                except urllib.error.HTTPError:
                    self._log.debug("Error while fetching book information from Audnex", exc_info=True)
            return out
        except Exception:
            self._log.warn("Error while fetching book information from Audnex", exc_info=True)
            return []

    def get_album_info(self, asin, region):
        """Returns an AlbumInfo object for a book given its asin."""

        (book, chapters) = get_book_info(asin, region)

        title = book.title
        subtitle = book.subtitle

        release_date = book.release_date
        series = book.series

        if series:
            series_name = series.name
            series_position = series.position

            title_cruft = f", Book {series_position}"
            if not self.config["keep_series_reference_in_title"] and title.endswith(title_cruft):
                # check if ', Book X' is in title, remove it
                self._log.debug(f"Title contains '{title_cruft}'. Removing it.")
                title = title.removesuffix(title_cruft)

            if series_position:
                album_sort = f"{series_name} {series_position} - {title}"
                content_group_description = f"{series_name}, Book #{series_position}"
            else:
                album_sort = f"{series_name} - {title}"
                content_group_description = None

            # clean up subtitle
            if (
                not self.config["keep_series_reference_in_subtitle"]
                and subtitle
                and series_name.lower() in subtitle.lower()
                and "book" in subtitle.lower()
            ):
                # subtitle contains both the series name and the word "book"
                # so it is likely just "Series, Book X" or "Book X in Series"
                # don't include subtitle
                subtitle = None
                self._log.debug(f"Subtitle of '{subtitle}' is mostly just the series name. Removing it.")

        elif subtitle:
            album_sort = f"{title} - {subtitle}"
        else:
            album_sort = title

        if not series:
            series_name = None
            series_position = None
            content_group_description = None

        authors = ", ".join([a.name for a in book.authors])
        narrators = ", ".join([n.name for n in book.narrators])
        authors_and_narrators = ", ".join([authors, narrators])
        artists = authors_and_narrators if self.config["include_narrator_in_artists"] else authors

        description = book.summary_markdown
        cover_url = book.image_url
        genres = "/".join([g.name for g in book.genres])

        album_url = get_audible_album_url(asin, book.region)
        region = book.region

        common_attributes = {
            "artist_id": None,
            "asin": asin,
            "album_sort": album_sort,
            "composer": narrators,
            "grouping": content_group_description,
            "genre": genres,
            "series_name": series_name,
            "series_position": series_position,
            "comments": description,
            "data_source": self.data_source,
            "subtitle": subtitle,
            "catalognum": asin,
            "album_url": album_url,
            "region": region,
        }

        tracks = [
            TrackInfo(
                track_id=None,
                index=i + 1,
                title=c.title,
                medium=1,
                artist=artists,
                length=c.length_ms / 1000,
                **common_attributes,
            )
            for i, c in enumerate(chapters.chapters)
        ]
        is_chapter_data_accurate = chapters.is_accurate

        # release_date is in in yyyy-mm-dd format
        year = int(release_date[:4])
        month = int(release_date[5:7])
        day = int(release_date[8:10])

        self.cover_art_urls[asin] = cover_url

        original_year = year
        original_month = month
        original_day = day

        if self.config["goodreads_apikey"]:
            original_date = get_original_date(self, asin, authors, title)
            if original_date.get("year") is not None:
                original_year = original_date.get("year")
                original_month = original_date.get("month")
                original_day = original_date.get("day")

        return AlbumInfo(
            tracks=tracks,
            album=title,
            album_id=asin,
            albumtype="audiobook",
            mediums=1,
            artist=authors,
            year=year,
            month=month,
            day=day,
            original_year=original_year,
            original_month=original_month,
            original_day=original_day,
            cover_url=cover_url,
            summary_html=book.summary_html,
            is_chapter_data_accurate=is_chapter_data_accurate,
            language=book.language,
            label=book.publisher,
            **common_attributes,
        )

    def track_for_id(self, track_id: str):
        self._log.debug("Searching for track {}", track_id)
        return None

    def item_candidates(self, item, artist, title):
        """Returns a list of TrackInfo objects for individual track search.

        Audiobooks are not searched by individual tracks, so this returns an empty list.
        """
        self._log.warn(
            "item_candidates returning empty list since searching for specific tracks in audiobooks doesn't make sense"
        )
        return []

    @staticmethod
    def on_write(item, path, tags):
        # Strip unwanted tags that Beets automatically adds
        tags["mb_albumid"] = None
        tags["mb_trackid"] = None
        tags["lyrics"] = None
        tags["bpm"] = None
        if path.endswith(b"m4b"):
            # audiobook media type, see https://exiftool.org/TagNames/QuickTime.html
            tags["desc"] = tags.get("comments")
            tags["itunes_media_type"] = 2
            if tags.get("series_name"):
                tags["show_movement"] = 1
            with suppress(Exception):
                # The "mvi" tag for m4b files only accepts integers
                tags["mvi"] = int(tags.get("series_position"))

    def fetch_art(self, session, task):
        # Only fetch art for albums
        if task.is_album:
            if task.album.artpath and os.path.isfile(task.album.artpath):
                # Album already has art (probably a re-import); skip it.
                return

            if task.choice_flag not in (importer.Action.APPLY, importer.Action.RETAG):
                return

            cover_url = self.cover_art_urls.get(task.album.asin)
            author = task.album.albumartist
            title = task.album.album
            if not cover_url:
                self._log.debug(f"No cover art found for {title} by {author}.")
                return

            try:
                cover_path = self.fetch_image(cover_url)
                self.cover_art[task] = cover_path
            except Exception:
                self._log.warn(
                    f"Error while downloading cover art for {title} by {author} from {cover_url}", exc_info=True
                )

    def fetch_image(self, url):
        """Downloads an image from a URL and returns a path to the downloaded image."""
        image = make_request(url)
        ext = url[-4:]  # e.g, ".jpg"
        with NamedTemporaryFile(suffix=ext, delete=False) as fh:
            fh.write(image)
        self._log.debug("downloaded art to: {0}", util.displayable_path(fh.name))
        return util.bytestring_path(fh.name)

    def on_import_task_files(self, task, session):
        self.write_book_description_and_narrator(task.imported_items())
        if self.config["fetch_art"] and task in self.cover_art:
            cover_path = self.cover_art.pop(task)
            task.album.set_art(cover_path, True)
            task.album.store()

    def write_book_description_and_narrator(self, items):
        """Write description.txt, reader.txt and cover art"""
        if len(items) == 0:
            return

        item = items[0]
        destination = os.path.dirname(item.path)

        if self.config["write_description_file"]:
            description = item.comments
            with open(os.path.join(destination, b"desc.txt"), "w") as f:
                f.write(description)

        if self.config["write_reader_file"]:
            narrator = item.composer
            with open(os.path.join(destination, b"reader.txt"), "w") as f:
                f.write(narrator)

    def on_import_task_created(self, session, task):
        """
        Remember the items for the current task so manual album ID lookups can align tracks.
        This is needed because album_for_id doesn't give us the items being imported
        """
        self._recent_items = list(task.items)

    def before_choose_candidate_event(self, session, task):
        return [PromptChoice("r", "Region switch", self.book_level_region_switch)]

    def book_level_region_switch(self, session, task):
        """Prompts the book level region value"""
        available_region_codes = ", ".join(ui.colorize("text_diff_added", reg) for reg in AUDIBLE_REGIONS)

        # config level region code
        current_config_region_code = self.config["region"].get()

        # book level region code
        book_region_code = get_item_region(task.items[0])
        if book_region_code is None:
            current_book_region_code = "--"
            ui_current_config_region_code = ui.colorize("text_highlight_minor", current_config_region_code)
            ui_current_book_region_code = ui.colorize("text_highlight_minor", current_book_region_code)
        else:
            current_book_region_code = book_region_code
            ui_current_config_region_code = ui.colorize("text_faint", current_config_region_code)
            ui_current_book_region_code = ui.colorize("text_highlight_minor", current_book_region_code)

        message = (
            f"Enter region code "
            f"({available_region_codes}) "
            f"[{ui_current_config_region_code}]"
            f"[{ui_current_book_region_code}]: "
        )

        color_name = "text_highlight_minor"
        region_code = ui.input_(message)

        if region_code in AUDIBLE_REGIONS:
            task.items[0]["region"] = region_code
            if current_book_region_code != region_code:
                color_name = "changed"
                current_book_region_code = region_code

        ui.print_("Current book region code:", ui.colorize(color_name, current_book_region_code))

        task.lookup_candidates()


def get_item_region(item):
    """Get the value of the 'region' field, if it is available, or can be extracted from 'album_url'."""
    available_field_names = item.keys()
    album_url = None
    region = None

    if "album_url" in available_field_names:
        album_url = item["album_url"]

    if "region" in available_field_names:
        region = item["region"]

    # The current value of the 'region' field takes precedence over the value extracted from the 'album_url' field.
    if (region is not None) and (region in AUDIBLE_REGIONS):
        result = region
    elif album_url is not None:
        result = get_audible_album_region(album_url)
    else:
        result = None
    return result
