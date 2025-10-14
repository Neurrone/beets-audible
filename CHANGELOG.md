# Changelog

## v1.1.0 (2025-10-14)

### Breaking Changes

- Bump Beets version requirement to v2.5.x instead of 2.x, since Beets makes breaking changes even for minor releases
- Bump minimum Python requirement to 3.9 to match Beets

### Fix

- Account for breaking changes in Beets 2.5.0

## v1.0.2 (2025-05-19)

### Fix

- Disable reading and writing of the `WOAF` tag for MP3 files to work around an [upstream bug in Beets](https://github.com/Neurrone/beets-audible/issues/71)

### Dependencies

- Bumped markdownify from 0.14 to be compatible with v1.x

## v1.0.1 (2024-12-19)

### Fix

- Loosen version constraints so that things like non-major Beets updates won't conflict with Beet-audible's dependency requirements

## v1.0.0 (2024-11-03)

### Breaking Changes

- Bump Beets version requirement to v2.0.0
- Bump minimum support Python version to 3.8

### Feature

- Add ability to remove series-related info from title and subtitle
- Add support for other Audible regions besides the US, which is the default

### Fix

- When rate-limited by Audible, use `retry-after` response header to wait the appropriate amount of time before retrying

## v0.1.0 (2022-11-27)

- Initial release
