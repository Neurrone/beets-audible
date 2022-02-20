import os
import re
from tempfile import NamedTemporaryFile

from beets import importer, util
from beets.autotag.hooks import AlbumInfo, TrackInfo
from beets.dbcore import types
from beets.plugins import BeetsPlugin, get_distance
import mediafile

from .api import get_book_info, make_request, search_audible

class Audible(BeetsPlugin):
    data_source = 'Audible'
    def __init__(self):
        super().__init__()

        self.config.add({
            'fetch_art': True,
            'source_weight': 0.0,
        })
        # Mapping of asin to cover art urls
        self.cover_art_urls = {}
        # stores paths of downloaded cover art to be used during import
        self.cover_art = {}
        
        self.register_listener('write', self.on_write)
        self.register_listener('import_task_files', self.on_import_task_files)
        
        if self.config['fetch_art']:
            self.import_stages = [self.fetch_art]
        
        # see https://github.com/beetbox/mediafile/blob/master/mediafile.py
        album_sort = mediafile.MediaField(
            mediafile.MP3StorageStyle(u'TSOA'),
            mediafile.StorageStyle(u'TSOA')
        )
        self.add_media_field('album_sort', album_sort)

        itunes_media_type = mediafile.MediaField(
            mediafile.MP3DescStorageStyle(u'ITUNESMEDIATYPE'),
            mediafile.StorageStyle(u'ITUNESMEDIATYPE')
        )
        self.add_media_field('itunes_media_type', itunes_media_type)

        series_name = mediafile.MediaField(
            mediafile.MP3StorageStyle(u'MVNM'),
            mediafile.MP3DescStorageStyle(u'SERIES'),
            mediafile.StorageStyle(u'MVNM')
        )
        self.add_media_field('series_name', series_name)
        series_position = mediafile.MediaField(
            mediafile.MP3StorageStyle(u'MVIN'),
            mediafile.MP3DescStorageStyle(u'SERIESPOSITION'),
            mediafile.StorageStyle(u'MVIN')
        )
        self.add_media_field('series_position', series_position)

        subtitle = mediafile.MediaField(
            mediafile.MP3StorageStyle(u'TIT3'),
            mediafile.StorageStyle(u'TIT3')
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
        if not album and not artist:
            self._log.debug('Skipping Audible query. Files missing album and '
                            'artist tags.')
            return []

        if va_likely:
            query = album
        else:
            query = f'{artist} {album}'
        albums = self.get_albums(query)
        for a in albums:
            is_chapter_data_accurate = a.is_chapter_data_accurate
            punctuation = r'[^\w\s\d]'
            normalized_book_title = re.sub(punctuation, '', a.album.strip().lower())
            normalized_album_name = re.sub(punctuation, '', album.strip().lower())
            # account for different length strings
            is_likely_match = normalized_album_name in normalized_book_title or normalized_book_title in normalized_album_name
            is_chapterized = len(a.tracks) == len(items)
            # matching doesn't work well if the number of files in the album doesn't match the number of chapters
            # As a workaround, return the same number of tracks as the number of files.
            # This white lie is a workaround but works extraordinarily well
            if is_likely_match and is_chapterized and not is_chapter_data_accurate:
                # Logging this for now because this situation 
                # is technically possible (based on the API) but unsure how often it happens
                self._log.warn(f"Chapter data for {a.album} could be inaccurate.")
            
            if is_likely_match and not is_chapterized:
                self._log.debug(f"Attempting to match non-chapterized book: album {album} with {len(items)} files to book {a.album} with {len(a.tracks)} chapters.")
                
                common_track_attributes = dict(a.tracks[0])
                del common_track_attributes['index']
                del common_track_attributes['length']
                del common_track_attributes['title']

                a.tracks = [
                    TrackInfo(**common_track_attributes, title=item.title, length=item.length, index=i+1)
                    for i, item in enumerate(items)
                ]
        return albums
    
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
        # Strip non-word characters from query. Things like "!" and "-" can
        # cause a query to return no results, even if they match the artist or
        # album title. Use `re.UNICODE` flag to avoid stripping non-english
        # word characters.
        query = re.sub(r'(?u)\W+', ' ', query)
        # Strip medium information from query, Things like "CD1" and "disk 1"
        # can also negate an otherwise positive result.
        query = re.sub(r'(?i)\b(CD|disc)\s*\d+', '', query)

        try:
            results = search_audible(query)
        except Exception as e:
            self._log.warn("Could not connect to Audible API while searching for {0!r}",
                            query, exc_info=True)
            return []
        
        try:
            products = results["products"]
            if len(products) > 0:
                return [self.get_album_info(p["asin"]) for p in products]
            else:
                return []
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
                content_group_description = f"{series_name}, book #{series_position}"
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
        
        authors = '/'.join([a.name for a in book.authors])
        narrators = '/'.join([n.name for n in book.narrators])
        authors_and_narrators = ', '.join([authors, narrators])
        description = book.summary_markdown
        cover_url = book.image_url
        genres = '/'.join([g.name for g in book.genres])

        common_attributes = {
            "artist_id": None, "asin":asin, "album_sort": album_sort,
            "composer": narrators, "grouping": content_group_description,
            "genre": genres, "series_name": series_name, "series_position": series_position,
            "comments": description, "data_source": self.data_source, "subtitle": subtitle,
        }

        tracks = [
            TrackInfo(
                track_id=None, index=i+1, title=c.title,
                artist=authors_and_narrators, length=c.length_ms / 1000,
                **common_attributes
            )
            for i, c in enumerate(chapters.chapters)
        ]
        is_chapter_data_accurate = chapters.is_accurate

        # release_date is in in yyyy-mm-dd format
        year = int(release_date[:4])
        month = int(release_date[5:7])
        day = int(release_date[8:10])
        mediums = []
        data_url = f"https://api.audnex.us/books/{asin}"

        self.cover_art_urls[asin] = cover_url
        return AlbumInfo(
            tracks=tracks, album=album, album_id=None, albumtype="audiobook",
            artist=authors, year=year, month=month, day=day,
            original_year=year, original_month=month, original_day=day,
            cover_url=cover_url, summary_html=book.summary_html,
            is_chapter_data_accurate=is_chapter_data_accurate,
            language=book.language, label=book.publisher, **common_attributes
        )
    
    def on_write(self, item, path, tags):
        tags["itunes_media_type"] = "Audiobook"
        # Strip unwanted tags that Beets automatically adds
        tags['mb_trackid'] = None
        tags['lyrics'] = None

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
                self._log.warn(f"No cover art found for {title} by {author}.")
            
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
        