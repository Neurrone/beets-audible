# Beets-audible: Organize Your Audiobook Collection With Beets

This is a plugin that allows Beets to manage audiobook collections.

It fetches audiobook metadata via the Audible and [Audnex API](https://github.com/laxamentumtech/audnexus). With this data, it ensures books have the correct tags and makes the collection ready to be served by Plex, Audiobookshelf or Booksonic.

## Motivation

[seanap's audiobook organization guide](https://github.com/seanap/Plex-Audiobook-Guide) describes a workflow for adding tags to audiobooks and moving the files to the right folders.

However, it relies on using Mp3tag, a gui tool which does not lend itself to automation. Mp3tag works only on Windows.

This Beets plugin solves both problems.

## Installation

To run from source, see [development setup](development.md)

1. Install via pip: `pip install beets-audible`. See the next section instead if you're running Beets in Docker (highly recommended as it makes it easier to maintain a separate Beets installation dedicated to audiobooks).
2. Use a separate beets config and database for managing audiobooks. This is the recommended Beets config for this plugin:

   ```yaml
   # add audible to the list of plugins
   # also add the "web" plugin if using the docker image
   plugins: audible edit fromfilename scrub

   directory: /audiobooks

   # Place books in their own folders to be compatible with Booksonic and Audiobookshelf servers
   paths:
     # For books that belong to a series
     "albumtype:audiobook series_name::.+ series_position::.+": $albumartist/%ifdef{series_name}/%ifdef{series_position} - $album%aunique{}/$track - $title
     "albumtype:audiobook series_name::.+": $albumartist/%ifdef{series_name}/$album%aunique{}/$track - $title
     # Stand-alone books
     "albumtype:audiobook": $albumartist/$album%aunique{}/$track - $title
     default: $albumartist/$album%aunique{}/$track - $title
     singleton: Non-Album/$artist - $title
     comp: Compilations/$album%aunique{}/$track - $title
     albumtype_soundtrack: Soundtracks/$album/$track $title

   # disables musicbrainz lookup, as it doesn't help for audiobooks
   musicbrainz:
     enabled: no

   audible:
     # if the number of files in the book is the same as the number of chapters from Audible,
     # attempt to match each file to an audible chapter
     match_chapters: true
     data_source_mismatch_penalty: 0.0 # disable the data_source_mismatch penalty
     fetch_art: true # whether to retrieve cover art
     include_narrator_in_artists: true # include author and narrator in artist tag. Or just author
     keep_series_reference_in_title: true # set to false to remove ", Book X" from end of titles
     keep_series_reference_in_subtitle: true # set to false to remove subtitle if it contains the series name and the word book ex. "Book 1 in Great Series", "Great Series, Book 1"
     write_description_file: true # output desc.txt
     write_reader_file: true # output reader.txt
     region:
       us # the region from which to obtain metadata can be omitted, by default it is "us"
       # pick one of the available values: au, ca, de, es, fr, in, it, jp, us, uk
       # the region value can be set for each book individually during import/re-import
       # also it is automatically derived from 'WOAF' (WWWAUDIOFILE) tag
       # which may contain a URL such as 'https://www.audible.com/pd/ASINSTRING' or 'audible.com'

   scrub:
     auto: yes # optional, enabling this is personal preference
   ```

3. Run the `beet --version` command and verify that the audible plugin appears in the list of plugins.

### With Docker

1. Create the following folder structure:

   ```
   beets
     config/
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
       image: lscr.io/linuxserver/beets:2.5.1-ls297
       container_name: beets-audible
       environment:
         # Update as needed
         - PUID=1000
         - PGID=1000
         - TZ=Asia/Singapore
       volumes:
         - ./config:/config
         - ./scripts:/custom-cont-init.d
         - /path/to/audiobooks:/audiobooks
         - /path/to/import/books/from:/input
       restart: unless-stopped
   ```

3. Save the following under `scripts/install-deps.sh`:

   ```sh
   #!/bin/bash
   echo "Installing dependencies..."
   pip install --no-cache-dir beets-audible
   ```

4. Spin up the container: `docker-compose up -d`
5. Update the config in `config/config.yaml` as described above.
6. In the docker container, run the `beet --version` command and verify that the audible plugin appears in the list of plugins.

## Usage

When importing audiobooks into Beets, ensure that the files for each book are in its own folder, even if the audiobook only consists of a single file. This is so that the files for a book are treated as an album by Beets. Avoid putting files from multiple books in the same folder.

When ready, start the import by executing the following command in the container:

```sh
beet import /path/to/audiobooks
```

The following sources of information are used to search for book matches in order of preference:

1. A file containing book info named `metadata.yml` (see below)
2. Album and artist tags
3. If tags are missing from the file, enabling the fromfilename plugin will attempt to deduce album and artist from file names
4. If all else fails, use the folder name as the query string

If you're not getting a match for a book, try the following:

1. Check the tags on the files being imported. The album and artist tags should be set to the book title and author respectively.
2. Press `E` when Beets prompts you about not being able to find a match. This prompts for the artist and album name. If the wrong book is being matched because there are other books with similar names on Audible, try using the audiobook's asin as the artist and title as the album.
3. Switch Audible service region to obtain metadata from:
   - Set `region` in the beets config.
   - Press `R` to set region for a book when Beets prompts you about not being able to find a match or if it is incorrect.
4. Specify the book's data by using `metadata.yml` if it isn't on Audible (see the next section).

The plugin gets chapter data of each book and tries to match them to the imported files if and only if the number of imported files is the same as the number of chapters from Audible. This can fail and cause inaccurate track assignments if the lengths of the files don't match Audible's chapter data. If this happens, set the config option `match_chapters` to `false` temporarily and try again, and remember to uncomment that line once done.

### Goodreads for original work first published date

The plugin can search Goodreads to find the original publication date of the work the audiobook is based on by searching on the ASIN. To enable this option you need a Goodreads API key and you must set that key in the audible plugin config

```
   audible:
     goodreads_apikey: [APIKEYHERE] #optional
```

If you want this date used as the release date for the audiobook, you must set [original_date](https://beets.readthedocs.io/en/stable/reference/config.html#original-date) to yes in your beets config

### Importing Non-Audible Content

The plugin looks for a file called `metadata.yml` in each book's folder during import. If this file is present, it exclusively uses the info in it for tagging and skips the Audible lookup.

This is meant for importing audio content that isn't on Audible.

Here's an example of what `metadata.yml` should look like:

```yaml
---
# These are all required fields
title: The Lord of the Rings (BBC Dramatization)
authors: ["J. R. R. Tolkien", "Brian Sibley", "Michael Bakewell"]
narrators:
  - "Ian Holm (as Frodo)"
  - "Sir Michael Hordern (as Gandalf)"
  - "Robert Stephens (as Aragorn)"
  - "John Le Mesurier"
description: |
  This audio set includes: The Fellowship of the Ring; The Two Towers; and The Return of the King.

  Undertaking the adaptation of J.R.R. Tolkien's best-known work was an enormous task, but with its first broadcast on BBC Radio 4 on March 8, 1981, this dramatized tale of Middle Earth became an instant global classic. Thrilling dramatization by Brian Sibley and Michael Bakewell it boasts a truly outstanding cast including Ian Holm (as Frodo), Sir Michael Hordern (as Gandalf), Robert Stephens (as Aragorn), and John Le Mesurier. Tolkiens tale relates the perilous attempt by Frodo Baggins and company to defeat the evil Saruman and dispose of the Ruling Ring. Brian Sibley wrote the opening and closing narration for the character of Frodo, played by Ian Holm, who now stars as Bilbo in the feature films based on The Lord of the Rings.
genres: ["fantasy"]
releaseDate: 2008-08-19
publisher: BBC Audiobooks

# optional fields
language: English # defaults to "English" if not specified
subtitle: "some subtitle"
series: The Lord Of The Rings
seriesPosition: "1-3"
```

## Folder Structure

The config above places books according to this folder structure, which can be changed by editing the path config.

```
Terry Goodkind/
  Sword of Truth/
    1 - Wizards First Rule/
      cover.png
      desc.txt
      reader.txt
      wizards first rule.m4b
George Orwell/
  Animal Farm/
    Animal Farm.m4b
    cover.png
    desc.txt
    reader.txt
```

Desc.txt and reader.txt contain the book description and narrator populated from Audible.

## Tags Written

The plugin writes the following tags:

| ID3 Tag                                  | Audible.com Value                                                                                                                   |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `TIT1` (CONTENTGROUP)                    | Series, Book #                                                                                                                      |
| `TALB` (ALBUM)                           | Title                                                                                                                               |
| `TIT3` (SUBTITLE)                        | Subtitle                                                                                                                            |
| `TPE1` (ARTIST)                          | Author, Narrator                                                                                                                    |
| `TPE2` (ALBUMARTIST)                     | Author                                                                                                                              |
| `TCOM` (COMPOSER)                        | Narrator                                                                                                                            |
| `TCON` (GENRE)                           | Genre1/Genre2                                                                                                                       |
| `TDRC` and `TDRL` (release date)         | audio publication date                                                                                                              |
| `COMM` or `desc` for m4b files (COMMENT) | Publisher's Summary                                                                                                                 |
| `TSOA` (ALBUMSORT)                       | If ALBUM only, then %Title%<br>If ALBUM and SUBTITLE, then %Title% - %Subtitle%<br>If Series, then %Series% %Series-part% - %Title% |
| `TPUB` (PUBLISHER)                       | Publisher                                                                                                                           |
| `ASIN` (ASIN)                            | Amazon Standard Identification Number                                                                                               |
| `WOAF` (WWWAUDIOFILE)                    | Audible Album URL                                                                                                                   |
| `stik` (media type), m4b only            | 2 (audiobook)                                                                                                                       |
| `shwm` (show movement), m4b only         | 1 if part of a series                                                                                                               |
| `MVNM` (MOVEMENTNAME)                    | Series                                                                                                                              |
| `MVIN` / `MVI` for m4b files (MOVEMENT)  | Series Book #                                                                                                                       |
| `TXXX_SERIES` (SERIES)                   | Series                                                                                                                              |
| `TXXX_SERIES-PART`                       | Series position                                                                                                                     |

## Known Limitations

1. Anything that would cause Beets to move data (e.g, if performing an update after changing the path format) only moves the audio files and cover, leaving desc.txt and reader.txt behind. They need to be moved manually. This is because Beets doesn't associate these files with the album in its database.

## Plex Integration

If the directory where Beets imports audiobooks to is also where you've set Plex to serve content from, you can enable the [plexupdate plugin](https://beets.readthedocs.io/en/stable/plugins/plexupdate.html) to notify Plex when new books are imported.
