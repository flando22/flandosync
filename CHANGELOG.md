# Changelog

## v1.5.0

- Added temporary download tokens returned by `/project_by_key`.
- File downloads now require a valid download token by default.
- Added per-token concurrent download limits.
- Added token expiration settings.
- Blocked direct HTTP access to sensitive server files such as keys and configs.

## v1.4.0

- Added manifest versioning controls to the server.
- Added optional manifest changelog text.
- Added client-side update warnings when the server version differs from the last synced version.
- The client now stores the last successfully synced modpack version.

## v1.3.1

- Added a modpack folder change action in the client context menu.
- Replaced manual theme text entry with a theme selector.
- Prevented long server test errors from stretching the settings dialog.
- Added admin panel security planning docs.

## v1.3.0

- Added manifest cache.
- Added retry/backoff for HTTP requests.
- Added configurable request timeout.
- Added limited parallel downloads.
- Added settings for manifest cache TTL, worker count, and timeout.

## v1.2.0

- Added client settings dialog.
- Added editable server URL in the UI.
- Added theme setting.
- Added server reachability test button.
- Settings are saved to `flandosync_settings.json`.

## v1.1.0

- Added modpack context menu in the client.
- Added local modpack aliases.
  - Display format: `Alias (server-name)`.
- Added modpack removal from the local list.
  - Optional synced-file deletion is available behind a confirmation checkbox.
  - File deletion is disabled by default.
- Added sync changes list.
  - Downloaded, skipped, and deleted files are shown separately from the console log.
- Added log export button.

## v1.0.0

- Initial public release.
- Python HTTP server.
- PyQt desktop client.
- Manifest generation.
- Access keys.
- Optional extra-file cleanup.
