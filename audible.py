from beets.autotag.hooks import AlbumInfo, TrackInfo
from beets.plugins import BeetsPlugin, get_distance
import mediafile
import re

from .api import get_book_info, search_audible
from .strip_html import strip_html

class Audible(BeetsPlugin):
    data_source = 'Audible'
    
    def __init__(self):
        super().__init__()
        self.register_listener('write', self.on_write)
        self.config.add({
            'source_weight': 0.5,
        })
        
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
            mediafile.MP3DescStorageStyle(u'SERIESPART'),
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
            normalized_book_title = a.album.strip().lower()
            normalized_album_name = album.strip().lower()
            # account for different length strings
            is_likely_match = normalized_album_name in normalized_book_title or normalized_book_title in normalized_album_name
            is_chapterized = len(a.tracks) == len(items)
            # matching doesn't work well if the number of files in the album doesn't match the number of chapters
            # As a workaround, return the same number of tracks as the number of files.
            # This white lie is a workaround but works extraordinarily well
            if is_likely_match and is_chapterized:
                self._log.debug(f"Attempting to match non-chapterized book: {len(items)} files to {len(a.tracks)} chapters.")
                
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
            products = results["products"]
            if len(products) > 0:
                return [self.get_album_info(p["asin"]) for p in products]
            else:
                return []
        except Exception as e:
            self._log.warn("Could not connect to Audible API while searching for {0!r}",
                            query, exc_info=True)
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
            album_sort = f"{series_name} {series_position} - {title}"
            content_group_description = f"{series_name}, book #{series_position}"
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
        description = strip_html(book.summary_html).replace(u'\xa0', u' ')
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

        # release_date is in in yyyy-mm-dd format
        year = release_date[:4]
        month = release_date[5:7]
        day = release_date[8:10]
        mediums = []
        data_url = f"https://api.audnex.us/books/{asin}"

        return AlbumInfo(
            tracks=tracks, album=album, album_id=None,
            artist=authors, year=year, month=month, day=day,
            summary_html=book.summary_html,
            language=book.language, **common_attributes
        )

    def on_write(self, item, path, tags):
        tags["itunes_media_type"] = "Audiobook"
