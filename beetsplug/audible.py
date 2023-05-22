import datetime
import os
import pathlib
import re
import urllib.error
from copy import deepcopy
from tempfile import NamedTemporaryFile
from typing import Dict, Iterable, List, Optional, Tuple

import beets.autotag.hooks
import Levenshtein
import mediafile
import yaml
from beets import importer, util
from beets.autotag.hooks import AlbumInfo, TrackInfo
from beets.library import Item
from beets.plugins import BeetsPlugin
from natsort import natsorted

from .api import get_book_info, make_request, search_audible
from .goodreads import get_original_date


def sort_items(items: List[Item]):
    naturally_sorted_items = natsorted(items, key=lambda i: i.title)
    return naturally_sorted_items


def get_common_data_attributes(track: TrackInfo) -> Dict:
    common_track_attributes = dict(track)
    del common_track_attributes["index"]
    del common_track_attributes["length"]
    del common_track_attributes["title"]
    return common_track_attributes


def convert_items_to_trackinfo(items: List[Item], common_attrs: Dict) -> List[TrackInfo]:
    out = []
    for i, item in enumerate(items, start=1):
        track = TrackInfo(**common_attrs, title=item.title, length=item.length, index=i)
        out.append(track)
    return out


def is_continuous_number_series(numbers: Iterable[Optional[int]]):
    return all([n is not None for n in numbers]) and all(b - a == 1 for a, b in zip(numbers, numbers[1:]))


def calculate_average_levenshtein_difference(tokens: List[str]) -> List[float]:
    out = []
    for token in tokens:
        temp = []
        for other in tokens:
            temp.append(Levenshtein.distance(token, other))
        num = len(tokens) - 1
        out.append(sum(temp) / num)
    return out


def find_regular_affixes(example_strings: List[str]) -> Tuple[str, str]:
    """Find regular prefixes and suffices that occur in most of the titles"""
    if len(example_strings) <= 1:
        return "", ""
    prefix_result = find_best_affix_sequence(example_strings)
    if prefix_result:
        prefix = _check_affix_commonness(prefix_result)
    else:
        prefix = ""

    reversed_strings = [e[::-1] for e in example_strings]
    suffix_result = find_best_affix_sequence(reversed_strings)
    if suffix_result:
        suffix = _check_affix_commonness(suffix_result)[::-1]
    else:
        suffix = ""

    return prefix, suffix


def _check_affix_commonness(affix_result: Tuple[str, float]) -> str:
    # the 75% is a magic number, done through testing
    if affix_result[1] >= 0.75:
        out = affix_result[0]
    else:
        out = ""
    return out


def find_best_affix_sequence(example_strings: List[str]) -> Optional[Tuple[str, float]]:
    affix_sequences = set()
    for s in example_strings:
        for i in range(0, len(s) + 1):
            affix_sequences.add(s[0:i])
    # filter to minimum affix length
    # 4 is a magic number
    filtered_affixes = filter(lambda p: len(p) >= 4, affix_sequences)
    affix_commonness = [(p, _check_affix_commonality(example_strings, rf"^{re.escape(p)}")) for p in filtered_affixes]
    if affix_commonness:
        sorted_affixes = sorted(affix_commonness, key=lambda p: (p[1], len(p[0])), reverse=True)
        affix = sorted_affixes[0]
        return affix
    else:
        return None


def _check_affix_commonality(tokens: List[str], pattern: str) -> float:
    matches = list(filter(None, [re.match(rf"{pattern}", t) for t in tokens]))
    total = len(matches)
    return total / len(tokens)


def strip_affixes(token: str, affixes: Tuple[str, str]) -> str:
    affixes = (re.escape(affixes[0]), re.escape(affixes[1]))
    token = re.sub(rf"^{affixes[0]}", "", token)
    token = re.sub(rf"{affixes[1]}$", "", token)
    return token


def check_starts_with_number(string: str) -> Optional[int]:
    pattern = re.compile(r"^(\d+)[ -_]")
    result = pattern.match(string)
    if result:
        try:
            number = result.group(1)
            number = int(number)
            return number
        except ValueError:
            pass


def specialised_levenshtein(token1: str, token2: str, ignored_affixes: Optional[Tuple[str, str]] = None) -> int:
    """Find the Levenshtein distance between two strings, penalising operations involving digits x10"""
    if ignored_affixes:
        token1 = strip_affixes(token1, ignored_affixes)
        token2 = strip_affixes(token2, ignored_affixes)
    operations = Levenshtein.editops(token1, token2)
    total_cost = 0
    for operation in operations:
        op, s1, s2 = operation
        if s1 >= len(token1):
            test1 = ""
        else:
            test1 = token1[s1]
        if s2 >= len(token2):
            test2 = ""
        else:
            test2 = token2[s2]
        if any([re.match(r"\d", s) for s in (test1, test2)]):
            total_cost += 10
        else:
            total_cost += 1
    return total_cost


class Audible(BeetsPlugin):
    data_source = "Audible"

    def __init__(self):
        super().__init__()

        self.config.add(
            {
                "chapter_matching_algorithms": [
                    "single_file",
                    "source_numbering",
                    "starting_numbers",
                    "natural_sort",
                    "chapter_levenshtein",
                ],
                "fetch_art": True,
                "match_chapters": True,
                "source_weight": 0.0,
                "write_description_file": True,
                "write_reader_file": True,
                "include_narrator_in_artists": True,
                "keep_series_reference_in_title": True,
                "keep_series_reference_in_subtitle": True,
                "goodreads_apikey": None,
                "trust_source_numbering": True,
            }
        )
        self.config["goodreads_apikey"].redact = True
        # Mapping of asin to cover art urls
        self.cover_art_urls = {}
        # stores paths of downloaded cover art to be used during import
        self.cover_art = {}

        self.register_listener("write", self.on_write)
        self.register_listener("import_task_files", self.on_import_task_files)

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

    def album_distance(self, items, album_info, mapping):
        dist = beets.autotag.hooks.Distance()
        return dist

    def track_distance(self, item, track_info):
        dist = beets.autotag.hooks.Distance()
        dist.add_string("track_title", item.title, track_info.title)
        return dist

    def attempt_match_trust_source_numbering(self, items: List[Item], album: AlbumInfo) -> Optional[List[Item]]:
        """If the input album is numbered and the number range is contiguous (doesn't skip any numbers), then trust
        that and start the index from 1 if it's not already."""
        sorted_tracks = sorted(items, key=lambda t: t.track)
        if is_continuous_number_series([t.track for t in sorted_tracks]):
            # if the track is zero indexed, re-number them
            if sorted_tracks[0].track != 1:
                matches = []
                for i, item in enumerate(sorted_tracks, start=1):
                    match = item
                    match.track = i
                    matches.append(match)
            else:
                matches = sorted_tracks
            return matches

    def attempt_match_starting_numbers(self, items: List[Item], album: AlbumInfo) -> Optional[List[Item]]:
        """Order tracks based on a starting number in the track name."""
        affixes = find_regular_affixes([c.title for c in items])
        stripped_titles = [strip_affixes(i.title, affixes) for i in items]

        starting_numbers = [check_starts_with_number(s) for s in stripped_titles]
        if all(starting_numbers) and is_continuous_number_series(sorted(starting_numbers)):
            items_with_numbers = list(zip(starting_numbers, items))
            matches = sorted(items_with_numbers, key=lambda i: i[0])
            matches = [i[1] for i in matches]
            return matches

    def attempt_match_natsort(self, items: List[Item], album: AlbumInfo) -> Optional[List[Item]]:
        """Use a natural sort on the input tracks to order them like a person would i.e. 10 is after 9, not 2."""
        affixes = find_regular_affixes([c.title for c in items])
        stripped_titles = [strip_affixes(i.title, affixes) for i in items]
        average_title_change = calculate_average_levenshtein_difference(stripped_titles)
        # magic number here, it's a judgement call
        if max(average_title_change) < 4:
            # can't assume that the tracks actually match even when there are the same number of items, since lengths
            # can be different e.g. an even split into n parts that aren't necessarily chapter-based so just natsort
            matches = natsorted(items, key=lambda t: t.title)
            return matches

    def attempt_match_chapter_levenshtein(self, items: List[Item], album: AlbumInfo) -> Optional[List[Item]]:
        """For every chapter in the input album, calculate the Levenshtein difference between every item in the online
        album and match each input track to the closest online track."""
        # Warning, this method is rather messy, and it's easy for this to go wrong.
        # This should be used as a last resort
        affixes = find_regular_affixes([c.title for c in items])

        all_remote_chapters: List = deepcopy(album.tracks)
        matches = []
        for chapter in items:
            # TODO: need a string distance algorithm that penalises number replacements more
            best_matches = list(
                sorted(
                    all_remote_chapters,
                    key=lambda c: specialised_levenshtein(chapter.title, c.title, affixes),
                )
            )
            best_match = best_matches[0]
            matches.append(best_match)
            all_remote_chapters.remove(best_match)
        return matches

    def attempt_match_single_item(self, items: List[Item], album: AlbumInfo) -> Optional[List[Item]]:
        """If the input album has a single item, use that; if the album also has a single item, prefer that."""
        if len(items) == 1:
            # Prefer a single named book from the remote source
            if len(album.tracks) == 1:
                matches = album.tracks
            else:
                matches = items
            return matches

    def sort_tracks(self, album: AlbumInfo, items: List[Item]) -> Optional[List[TrackInfo]]:
        common_attrs = get_common_data_attributes(album.tracks[0])

        # this is the master list of different approaches
        # must be updated for any additional options added in the future
        possible_matching_algorithms = {
            "single_file": self.attempt_match_single_item,
            "source_numbering": self.attempt_match_trust_source_numbering,
            "starting_numbers": self.attempt_match_starting_numbers,
            "natural_sort": self.attempt_match_natsort,
            "chapter_levenshtein": self.attempt_match_chapter_levenshtein,
        }
        for algorithm_choice in self.config["chapter_matching_algorithms"]:
            if algorithm_choice not in possible_matching_algorithms.keys():
                self._log.error(f"'{algorithm_choice}' is not a valid algorithm choice for chapter matching")
                return
            function = possible_matching_algorithms[algorithm_choice]
            matches = function(items, album)
            if matches is not None:
                tracks = convert_items_to_trackinfo(matches, common_attrs)
                return tracks
        # if len(items) > len(album.tracks):
        #     # TODO: find a better way to handle this
        #     # right now just reject this match
        #     return None

    def candidates(self, items, artist, album, va_likely, extra_tags=None):
        """Returns a list of AlbumInfo objects for Audible search results
        matching an album and artist (if not various).
        """
        folder_path = pathlib.Path(items[0].path.decode()).parent
        yml_metadata_file_path = folder_path / "metadata.yml"
        if yml_metadata_file_path.is_file():
            self._log.debug("Reading data from metadata.yml")
            try:
                with open(str(yml_metadata_file_path)) as f:
                    data = yaml.load(f, Loader=yaml.SafeLoader)
                    return [self.get_album_from_yaml_metadata(data, items)]
            except Exception as e:
                self._log.error("Error while reading data from metadata.yml", exc_info=True)
                return []

        if not album and not artist:
            folder_name = folder_path.name
            self._log.warn(f"Files missing album and artist tags. Attempting query based on folder name {folder_name}")
            query = folder_name
        else:
            if va_likely:
                query = album
            else:
                query = f"{album} {artist}"

        # Strip medium information from query, Things like "CD1" and "disk 1"
        # can also negate an otherwise positive result.
        query = re.sub(r"(?i)\b(CD|disc)\s*\d+", "", query)
        # Strip "(unabridged)" or "(abridged)"
        abridged_indicator = r"(?i)\((unabridged|abridged)\)"
        query = re.sub(abridged_indicator, "", query)

        self._log.debug(f"Searching Audible for {query}")
        albums = self.get_albums(query)
        for a in albums:
            a.tracks = self.sort_tracks(a, items)
        albums = list(filter(lambda a: a.tracks is not None, albums))
        return albums

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
        if self.config["include_narrator_in_artists"]:
            artists = authors_and_narrators
        else:
            artists = authors

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
        }

        naturally_sorted_items = sort_items(items)
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
            return self.get_album_info(asin)
        except Exception as E:
            # TODO: handle errors properly and distinguish between general errors and 404s
            self._log.debug(f"Exception while getting book {asin}")
            return None

    def get_albums(self, query):
        """Returns a list of AlbumInfo objects for an Audible search query."""
        try:
            results = search_audible(query)
        except Exception as e:
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
                    out.append(self.get_album_info(p["asin"]))
                except urllib.error.HTTPError:
                    self._log.debug("Error while fetching book information from Audnex", exc_info=True)
            return out
        except Exception as e:
            self._log.warn("Error while fetching book information from Audnex", exc_info=True)
            return []

    def get_album_info(self, asin):
        """Returns an AlbumInfo object for a book given its asin."""
        (book, chapters) = get_book_info(asin)

        title = book.title
        subtitle = book.subtitle

        release_date = book.release_date
        series = book.series

        if series:
            series_name = series.name
            series_position = series.position

            title_cruft = f", Book {series_position}"
            if not self.config['keep_series_reference_in_title'] and title.endswith(title_cruft):
                # check if ', Book X' is in title, remove it
                self._log.debug(f"Title contains '{title_cruft}'. Removing it.")
                title = title.removesuffix(title_cruft)

            if series_position:
                album_sort = f"{series_name} {series_position} - {title}"
                content_group_description = f"{series_name}, Book #{series_position}"
            else:
                album_sort = f"{series_name} - {title}"
                content_group_description = None

            #clean up subtitle
            if not self.config['keep_series_reference_in_subtitle'] and subtitle and series_name.lower() in subtitle.lower() and 'book' in subtitle.lower():
                #subtitle contains both the series name and the word "book"
                #so it is likely just "Series, Book X" or "Book X in Series"
                #don't include subtitle
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
        if self.config["include_narrator_in_artists"]:
            artists = authors_and_narrators
        else:
            artists = authors

        description = book.summary_markdown
        cover_url = book.image_url
        genres = "/".join([g.name for g in book.genres])

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
        data_url = f"https://api.audnex.us/books/{asin}"

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
            try:
                # The "mvi" tag for m4b files only accepts integers
                tags["mvi"] = int(tags.get("series_position"))
            except Exception:
                pass

    def fetch_art(self, session, task):
        # Only fetch art for albums
        if task.is_album:
            if task.album.artpath and os.path.isfile(task.album.artpath):
                # Album already has art (probably a re-import); skip it.
                return

            if task.choice_flag not in (importer.action.APPLY, importer.action.RETAG):
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
            except Exception as e:
                self._log.warn(f"Error while downloading cover art for {title} by {author} from {cover_url}: {e}")

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
