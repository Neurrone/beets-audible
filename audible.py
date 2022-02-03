from beets.autotag.hooks import AlbumInfo
from beets.plugins import BeetsPlugin, get_distance, MetadataSourcePlugin
import re
from .utils import search_audible

class Audible(BeetsPlugin):
    def album_distance(self, items, album_info, mapping):
        return get_distance(
            data_source='Audible',
            info=album_info,
            config=self.config
        )

    def candidates(self, items, artist, album, va_likely, extra_tags=None):
        """Returns a list of AlbumInfo objects for discogs search results
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
        res =  self.get_albums(query)
        print(res)
        return res

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
            self._log.debug("Communication error while searching for {0!r}",
                            query, exc_info=True)
            return []
        return [album for album in map(self.get_album_info, results["products"])
                if album]
    
    def get_album_info(self, result):
        """Returns an AlbumInfo object for an Audible search result.
        """
        
        artist, artist_id = MetadataSourcePlugin.get_artist(
            [{"id": a["asin"], "name": a["name"]} for a in result["authors"]],
        )
        title = result["title"]
        asin = result["asin"]
        release_date = result["release_date"]
        series = result["series"]
        if series and len(series) > 0:
            series_title = series[0]["title"]
            series_position = series[0]["sequence"]
            album = f"{series_title} {series_position}"
        else:
            album = title
        album_id = asin
        tracks = [] # TODO: support chapters

        # Extract information for the optional AlbumInfo fields, if possible.
        year = release_date[:4] # in yyyy-mm-dd format
        mediums = []
        data_url = f"https://api.audnex.us/books/{asin}"
        
        return AlbumInfo(album=album, album_id=album_id, artist=artist,
            artist_id=artist_id, year=year, tracks=tracks,
            data_source='Audible', data_url=data_url,
            asin=asin)