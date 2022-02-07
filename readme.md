# Beets-audible: Organize Your Audiobook Collection With Beets

This is a beets plugin that fetches audiobook metadata via the Audible and [Audnex API](https://github.com/laxamentumtech/audnexus).

Files are tagged following [seanap's suggested organization scheme](https://github.com/seanap/Plex-Audiobook-Guide). Note that writing cover art, description.txt and reader.txt have not been implemented yet.

## Limitations

Beets has some [limitations which affect audiobook management](https://github.com/beetbox/beets/discussions/4269). Mainly, the plugin will only work when the audiobooks being imported to Beets have already been chapterized. This is because Beets uses individual data for each track in an album (i.e, chapter data) to determine matches, and also assumes that a track maps to a file on the filesystem.

Hence, the following types of audio will not be recognized properly:

- A book as a single file with embedded chapter metadata. This is most commonly seen in .m4b files.
- A folder of MP3s which have not been chapterized (1 file per chapter).

## Installation

1. Clone this directory
2. Use a separate beets config and database for managing audiobooks. Edit the Beets config so that it includes the following:

   ```yaml
   # add audible to the list of plugins
   plugins: edit web audible

   musicbrainz:
     # disables musicbrainz lookup
     # This is a workaround, as there is currently no built-in way of doing so
     # see https://github.com/beetbox/beets/issues/400
     host: localhost:5123

   pluginpath:
     - /plugins/audible # the directory which contains audible.py

   audible:
     # disable the source_weight penalty
     source_weight: 0.0
   ```
