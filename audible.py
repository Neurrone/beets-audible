import datetime
import os
import pathlib
import re
from tempfile import NamedTemporaryFile
import yaml

from beets import importer, util
from beets.autotag.hooks import AlbumInfo, TrackInfo
from beets.dbcore import types
from beets.plugins import BeetsPlugin, get_distance
import mediafile
from natsort import os_sorted

from .api import get_book_info, make_request, search_audible, search_goodreads

class Audible(BeetsPlugin):
    data_source = 'Audible'
    def __init__(self):
        super().__init__()

        self.config.add({
            'fetch_art': True,
            'match_chapters': True,
            'source_weight': 0.0,
            'include_narrator_in_artists': True,
            'goodreads_apikey': None
        })
        self.config['goodreads_apikey'].redact = True
        # Mapping of asin to cover art urls
        self.cover_art_urls = {}
        # stores paths of downloaded cover art to be used during import
        self.cover_art = {}

        self.register_listener('write', self.on_write)
        self.register_listener('import_task_files', self.on_import_task_files)
        
        if self.config['fetch_art']:
            self.import_stages = [self.fetch_art]
        
        # see the following:
        # Beet's internal mapping to tags: https://github.com/beetbox/mediafile/blob/master/mediafile.py
        # Mp3tag's mapping: https://docs.mp3tag.de/mapping/
        # Tag Mapping from the Hydrogenaudio Knowledgebase: https://wiki.hydrogenaud.io/index.php?title=Tag_Mapping
        # List of M4b tags: https://mutagen.readthedocs.io/en/latest/api/mp4.html
        album_sort = mediafile.MediaField(
            mediafile.MP3StorageStyle(u'TSOA'),
            mediafile.MP4StorageStyle('soal'),
            mediafile.StorageStyle(u'TSOA'),
            mediafile.ASFStorageStyle('WM/AlbumSortOrder'),
        )
        self.add_media_field('album_sort', album_sort)
        desc = mediafile.MediaField(
            mediafile.MP4StorageStyle('desc')
        )
        self.add_media_field('desc', desc)
        itunes_media_type = mediafile.MediaField(
            mediafile.MP4StorageStyle('stik', as_type=int),
        )
        self.add_media_field('itunes_media_type', itunes_media_type)
        show_movement = mediafile.MediaField(
            mediafile.MP4StorageStyle('shwm', as_type=int),
        )
        self.add_media_field('show_movement', show_movement)

        series_name = mediafile.MediaField(
            mediafile.MP3StorageStyle(u'MVNM'),
            mediafile.MP3DescStorageStyle(u'SERIES'),
            mediafile.MP4StorageStyle('\xa9mvn'),
            mediafile.MP4StorageStyle('----:com.apple.iTunes:SERIES'),
            mediafile.StorageStyle(u'MVNM')
        )
        self.add_media_field('series_name', series_name)
        series_position = mediafile.MediaField(
            mediafile.MP3StorageStyle(u'MVIN'),
            mediafile.MP3DescStorageStyle(u'SERIES-PART'),
            # Using the "mvi" tag for M4b wouldn't work when the value can't be converted to an integer
            # For instance, an m4b containing multiple books has series position "1-3"
            # Trying to do so would cause an exception, hence why this is commented out here
            # and handled below separately
            # mediafile.MP4StorageStyle('\xa9mvi'),
            mediafile.MP4StorageStyle('----:com.apple.iTunes:SERIES-PART'),
            mediafile.StorageStyle(u'MVIN')
        )
        self.add_media_field('series_position', series_position)
        mvi = mediafile.MediaField(
            mediafile.MP4StorageStyle('\xa9mvi', as_type=int),
        )
        self.add_media_field('mvi', mvi)

        subtitle = mediafile.MediaField(
            mediafile.MP3StorageStyle(u'TIT3'),
            mediafile.MP4StorageStyle('----:com.apple.iTunes:SUBTITLE'),
            mediafile.StorageStyle(u'TIT3'),
            mediafile.ASFStorageStyle('WM/SubTitle'),
        )
        self.add_media_field('subtitle', subtitle)

    def album_distance(self, items, album_info, mapping):
        dist =  get_distance(
            data_source=self.data_source,
            info=album_info,
            config=self.config
        )
        return dist

    def track_distance(self, item, track_info):
        return get_distance(
            data_source=self.data_source,
            info=track_info,
            config=self.config
        )

    def candidates(self, items, artist, album, va_likely, extra_tags=None):
        """Returns a list of AlbumInfo objects for Audible search results
        matching an album and artist (if not various).
        """
        folder_path = pathlib.Path(items[0].path.decode()).parent
        ymlMetadataFilePath = folder_path / 'metadata.yml'
        if ymlMetadataFilePath.is_file():
            self._log.debug("Reading data from metadata.yml")
            try:
                with open(str(ymlMetadataFilePath)) as f:
                    data = yaml.load(f, Loader=yaml.SafeLoader)
                    return [self.getAlbumFromYamlMetadata(data, items)]
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
                query = f'{album} {artist}'
        
        # Strip medium information from query, Things like "CD1" and "disk 1"
        # can also negate an otherwise positive result.
        query = re.sub(r'(?i)\b(CD|disc)\s*\d+', '', query)
        # Strip "(unabridged)" or "(abridged)"
        abridged_indicator = r'(?i)\((unabridged|abridged)\)'
        query = re.sub(abridged_indicator, '', query)
        
        self._log.debug(f"Searching Audible for {query}")
        albums = self.get_albums(query)
        for a in albums:
            is_chapter_data_accurate = a.is_chapter_data_accurate
            punctuation = r'[^\w\s\d]'
            # normalize by removing punctuation, converting to lowercase,
            # as well as changing multiple consecutive spaces in the string to a single space
            normalized_book_title = re.sub(punctuation, '', a.album.strip().lower())
            normalized_book_title = " ".join(normalized_book_title.split())
            normalized_album_name = re.sub(abridged_indicator, '', album.strip().lower())
            normalized_album_name = re.sub(punctuation, '', normalized_album_name)
            
            normalized_album_name = " ".join(normalized_album_name.split())
            self._log.debug(f"Matching album name {normalized_album_name} with book title {normalized_book_title}")
            # account for different length strings
            is_likely_match = normalized_album_name in normalized_book_title or normalized_book_title in normalized_album_name
            is_chapterized = len(a.tracks) == len(items)
            # matching doesn't work well if the number of files in the album doesn't match the number of chapters
            # As a workaround, return the same number of tracks as the number of files.
            # This white lie is a workaround but works extraordinarily well
            if self.config['match_chapters'] and is_likely_match and is_chapterized and not is_chapter_data_accurate:
                # Logging this for now because this situation 
                # is technically possible (based on the API) but unsure how often it happens
                self._log.warn(f"Chapter data for {a.album} could be inaccurate.")
            
            if is_likely_match and (not is_chapterized or not self.config['match_chapters']):
                self._log.debug(f"Attempting to match book: album {album} with {len(items)} files to book {a.album} with {len(a.tracks)} chapters.")
                
                common_track_attributes = dict(a.tracks[0])
                del common_track_attributes['index']
                del common_track_attributes['length']
                del common_track_attributes['title']

                # Ignore existing track numbers, and instead sort based on file path
                # Use natural sorting instead of lexigraphical to avoid this order:
                # chapter 1, 10, 12, ..., 19, 2, etc
                # This does work correctly when the album has multiple disks
                # using the bytestring_path function from Beets is needed for correctness
                # I was noticing inaccurate sorting if using str to convert paths to strings
                naturally_sorted_items = os_sorted(items, key=lambda i: util.bytestring_path(i.path))
                a.tracks = [
                    TrackInfo(**common_track_attributes, title=item.title, length=item.length, index=i+1)
                    for i, item in enumerate(naturally_sorted_items)
                ]
        return albums
    
    def getAlbumFromYamlMetadata(self, data, items):
        """Returns an `AlbumInfo` object by populating it with details from metadata.yml
        """
        title = data['title']
        subtitle = data.get('subtitle')
        release_date = data['releaseDate']
        series_name = data.get('series')
        series_position = data.get('seriesPosition')
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
        
        authors = ', '.join(data['authors'])
        narrators = ', '.join(data['narrators'])
        authors_and_narrators = ', '.join([authors, narrators])
        if self.config['include_narrator_in_artists']:
            artists = authors_and_narrators
        else:
            artists = authors        

        description = data['description']
        genres = '/'.join(data['genres'])

        common_attributes = {
            "artist_id": None, "album_sort": album_sort, "composer": narrators,
            "grouping": content_group_description, "genre": genres,
            "series_name": series_name, "series_position": series_position,
            "comments": description, "data_source": "YAML", "subtitle": subtitle,
        }

        naturally_sorted_items = os_sorted(items, key=lambda i: util.bytestring_path(i.path))
        # populate tracks by using some of the info from the files being imported
        tracks = [
            TrackInfo(
                **common_attributes, track_id=None, artist=artists, 
                index=i+1, length=item.length, title=item.title, medium=1
            )    
            for i, item in enumerate(naturally_sorted_items)
        ]

        year = release_date.year
        month = release_date.month
        day = release_date.day
        language = data.get('language', 'English')
        publisher = data['publisher']

        return AlbumInfo(
            tracks=tracks, album=title, album_id=None, albumtype="audiobook", mediums=1,
            artist=authors, year=year, month=month, day=day,
            original_year=year, original_month=month, original_day=day,
            language=language, label=publisher, **common_attributes
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
        """Returns a list of AlbumInfo objects for an Audible search query.
        """
        try:
            results = search_audible(query)
        except Exception as e:
            self._log.warn("Could not connect to Audible API while searching for {0!r}",
                            query, exc_info=True)
            return []
        
        try:
            products = results["products"]
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            products_without_unreleased_entries = [
                p for p in products if p["release_date"] <= today
            ]
            if len(products_without_unreleased_entries) < len(products):
                # see https://github.com/laxamentumtech/audnexus/issues/239
                self._log.info(f"Excluded {len(products) - len(products_without_unreleased_entries)} books which have not been released from consideration.")
            
            return [self.get_album_info(p["asin"]) for p in products_without_unreleased_entries]
        except Exception as e:
            self._log.warn("Error while fetching book information from Audnex",
                            exc_info=True)
            return []
        
    def get_album_info(self, asin):
        """Returns an AlbumInfo object for a book given its asin.
        """
        (book, chapters) = get_book_info(asin)
        
        title = book.title
        subtitle = book.subtitle
        
        release_date = book.release_date
        series = book.series
        album = title
        
        if series:
            series_name = series.name
            series_position = series.position
            if series_position:
                album_sort = f"{series_name} {series_position} - {title}"
                content_group_description = f"{series_name}, Book #{series_position}"
            else:
                album_sort = f"{series_name} - {title}"
                content_group_description = None
        elif subtitle:
            album_sort = f"{title} - {subtitle}"
        else:
            album_sort = title
        
        if not series:
            series_name = None
            series_position = None
            content_group_description = None
        
        authors = ', '.join([a.name for a in book.authors])
        narrators = ', '.join([n.name for n in book.narrators])
        authors_and_narrators = ', '.join([authors, narrators])
        if self.config['include_narrator_in_artists']:
            artists = authors_and_narrators
        else:
            artists = authors

        description = book.summary_markdown
        cover_url = book.image_url
        genres = '/'.join([g.name for g in book.genres])

        common_attributes = {
            "artist_id": None, "asin":asin, "album_sort": album_sort,
            "composer": narrators, "grouping": content_group_description,
            "genre": genres, "series_name": series_name, "series_position": series_position,
            "comments": description, "data_source": self.data_source, "subtitle": subtitle,
            "catalognum": asin
        }

        tracks = [
            TrackInfo(
                track_id=None, index=i+1, title=c.title, medium=1,
                artist=artists, length=c.length_ms / 1000,
                **common_attributes
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

        original_year=year
        original_month=month
        original_day=day

        if self.config['goodreads_apikey']:
            original_date = search_goodreads(asin, self.config['goodreads_apikey'])
            if original_date.get("year") is not None:
                original_year=original_date.get("year")
                original_month=original_date.get("month")
                original_day=original_date.get("day")
        
        return AlbumInfo(
            tracks=tracks, album=album, album_id=asin, albumtype="audiobook", mediums=1,
            artist=authors, year=year, month=month, day=day,
            original_year=original_year, original_month=original_month, original_day=original_day,
            cover_url=cover_url, summary_html=book.summary_html,
            is_chapter_data_accurate=is_chapter_data_accurate,
            language=book.language, label=book.publisher, **common_attributes
        )
    
    def on_write(self, item, path, tags):
        # Strip unwanted tags that Beets automatically adds
        tags['mb_albumid'] = None
        tags['mb_trackid'] = None
        tags['lyrics'] = None
        tags['bpm'] = None
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
            
            if not task.choice_flag in (importer.action.APPLY,
                                      importer.action.RETAG):
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
        """Downloads an image from a URL and returns a path to the downloaded image.
        """
        image = make_request(url)
        ext = url[-4:] # e.g, ".jpg"
        with NamedTemporaryFile(suffix=ext, delete=False) as fh:
            fh.write(image)
        self._log.debug('downloaded art to: {0}',
                        util.displayable_path(fh.name))
        return util.bytestring_path(fh.name)

    def on_import_task_files(self, task, session):
        self.write_book_description_and_narrator(task.imported_items())
        if self.config['fetch_art'] and task in self.cover_art:
            cover_path = self.cover_art.pop(task)
            task.album.set_art(cover_path, True)
            task.album.store()
    
    def write_book_description_and_narrator(self, items):
        """Write description.txt, reader.txt and cover art
        """
        if len(items) == 0:
            return
        
        item = items[0]
        destination = os.path.dirname(item.path)
        
        description = item.comments
        with open(os.path.join(destination, b'desc.txt'), 'w') as f:
            f.write(description)
        
        narrator = item.composer
        with open(os.path.join(destination, b'reader.txt'), 'w') as f:
            f.write(narrator)
        
