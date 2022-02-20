# Beets-audible: Organize Your Audiobook Collection With Beets

This is a plugin that allows Beets to manage audiobook collections.

It fetches audiobook metadata via the Audible and [Audnex API](https://github.com/laxamentumtech/audnexus). With this data, it ensures books have the correct tags and makes the collection ready to be served by Plex, Audiobookshelf or Booksonic.

## Motivation

[seanap's audiobook organization guide](https://github.com/seanap/Plex-Audiobook-Guide) describes a workflow for adding tags to audiobooks and moving the files to the right folders.

However, it relies on using Mp3tag, a gui tool which does not lend itself to automation. Mp3tag works only on Windows.

This Beets plugin solves both problems.

## Installation

1. Clone this repository.
2. Install markdownify from pip: `pip install markdownify`. See the next section instead if you're running Beets in Docker (highly recommended as it makes it easier to maintain a separate Beets installation dedicated to audiobooks).
3. Use a separate beets config and database for managing audiobooks. This is the recommended Beets config for this plugin:

   ```yaml
   # add audible to the list of plugins
   plugins: edit scrub audible

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
       install-markdownify.sh # see step 3
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
         - ./scripts:/config/custom-cont-init.d
         - /path/to/audiobooks:/music
         - /path/where/books/are/imported/from:/downloads
         - ./plugins:/plugins
       restart: unless-stopped
   ```

3. Save the following under `scripts/install-markdownify.sh`:

   ```sh
   #!/bin/bash
   echo "Installing markdownify"
   pip install markdownify
   ```

4. Clone this repository into the `plugins` folder.
5. Spin up the container: `docker-compose up -d`
6. Update the config in `config/config.yaml` as described above.
7. Run the `beet --version` command and verify that the audible plugin appears in the list of plugins.

## Usage

When importing audiobooks into Beets, ensure that the files for each book are in its own folder. This is so that the files for a book are treated as an album by Beets. Avoid putting files from multiple books in the same folder.
