# Changelog

<!--next-version-placeholder-->

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
