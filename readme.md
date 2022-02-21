# Beets-audible: Organize Your Audiobook Collection With Beets

This is a plugin that allows Beets to manage audiobook collections.

It fetches audiobook metadata via the Audible and [Audnex API](https://github.com/laxamentumtech/audnexus). With this data, it ensures books have the correct tags and makes the collection ready to be served by Plex, Audiobookshelf or Booksonic.

## Motivation

[seanap's audiobook organization guide](https://github.com/seanap/Plex-Audiobook-Guide) describes a workflow for adding tags to audiobooks and moving the files to the right folders.

However, it relies on using Mp3tag, a gui tool which does not lend itself to automation. Mp3tag works only on Windows.

This Beets plugin solves both problems.

## Installation

1. Clone this repository.
2. Install dependencies via pip: `pip install markdownify natsort`. See the next section instead if you're running Beets in Docker (highly recommended as it makes it easier to maintain a separate Beets installation dedicated to audiobooks).
3. Use a separate beets config and database for managing audiobooks. This is the recommended Beets config for this plugin:

   ```yaml
   # add audible to the list of plugins
   plugins: edit fromfilename scrub audible

   directory: /audiobooks

   # Place books in their own folders to be compatible with Booksonic and Audiobookshelf servers
   paths:
     # For books that belong to a series
     "albumtype:audiobook series_name::.+": $albumartist/%ifdef{series_name}/$year - $album%aunique{} [%ifdef{series_name} %ifdef{series_position}]/$track - $title
     # Stand-alone books
     "albumtype:audiobook": $albumartist/$year - $album%aunique{}/$track - $title
     default: $albumartist/$album%aunique{}/$track - $title
     singleton: Non-Album/$artist - $title
     comp: Compilations/$album%aunique{}/$track - $title
     albumtype_soundtrack: Soundtracks/$album/$track $title

   # disables musicbrainz lookup, as it doesn't help for audiobooks
   # This is a workaround, as there is currently no built-in way of doing so
   # see https://github.com/beetbox/beets/issues/400
   musicbrainz:
     host: localhost:5123

   pluginpath:
     - /plugins/audible # point this to the directory which contains audible.py

   audible:
     source_weight: 0.0 # disable the source_weight penalty
     fetch_art: true # whether to retrieve cover art

   scrub:
     auto: yes # optional, enabling this is personal preference
   ```

4. Run the `beet --version` command and verify that the audible plugin appears in the list of plugins.

### With Docker

1. Create the following folder structure:

   ```
   beets
     config/
     plugins/
     scripts/
       install-deps.sh # see step 3
     docker-compose.yml # see step 2
   ```

2. Save the following as the docker-compose file:

   ```yaml
   ---
   version: "3"
   services:
     beets:
       image: lscr.io/linuxserver/beets:latest
       container_name: beets
       environment:
         # Update as needed
         - PUID=1000
         - PGID=1000
         - TZ=Asia/Singapore
       volumes:
         - ./config:/config
         - ./plugins:/plugins
         - ./scripts:/config/custom-cont-init.d
         - /path/to/audiobooks:/audiobooks
         - /path/to/import/books/from:/input
       restart: unless-stopped
   ```

3. Save the following under `scripts/install-deps.sh`:

   ```sh
   #!/bin/bash
   echo "Installing dependencies..."
   pip install markdownify natsort
   ```

4. Clone this repository into the `plugins` folder.
5. Spin up the container: `docker-compose up -d`
6. Update the config in `config/config.yaml` as described above.
7. Run the `beet --version` command and verify that the audible plugin appears in the list of plugins.

## Usage

When importing audiobooks into Beets, ensure that the files for each book are in its own folder. This is so that the files for a book are treated as an album by Beets. Avoid putting files from multiple books in the same folder.

The following sources of information are used to search for book matches in order of preference:

1. Album and artist tags
2. If tags are missing from the file, enabling the fromfilename plugin will attempt to deduce album and artist from file names
3. If all else fails, use the folder name as the query string

If you're not getting a match for a book, chances are that it is bad data in tags. Correct the artist and album tags before trying again.

## Plex Integration

If the directory where Beets imports audiobooks to is also where you've set Plex to serve content from, you can enable the [plexupdate plugin](https://beets.readthedocs.io/en/stable/plugins/plexupdate.html) to notify Plex when new books are imported.
