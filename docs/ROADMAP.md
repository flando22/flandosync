# Flandosync Roadmap

This document tracks planned features and a recommended implementation order.

## v1.1.0 - Client Usability

- Modpack context menu. Done.
- Local modpack alias. Done.
  - Example display: `My Pack (aerocraft)`.
- Remove modpack from the local list. Done.
  - Show a confirmation dialog.
  - Optional checkbox: `Also permanently delete modpack files`.
  - Checkbox is disabled by default.
- Export logs from the UI. Done.
- Better sync result summary. Done.
  - Downloaded files.
  - Skipped files.
  - Deleted extra files.
- Basic UX pass. In progress.

## v1.2.0 - Client Settings

- Settings dialog. Done.
- Server URL setting. Done.
- Theme setting. Done.
- Save settings to `flandosync_settings.json`. Done.
- Test server connection from the settings dialog. Done.

## v1.3.0 - Stability And Performance

- Manifest cache. Done.
- Limited parallel downloads. Done.
- Better timeouts and retries. Done.
- Safer behavior when the network fails. In progress.

## v1.4.0 - Modpack Versioning

- Add modpack version to the manifest.
- Store the last synced version on the client.
- Warn users when an update is available.
- Show changelog when available.

## v1.5.0 - Access Limits

Possible approaches:

- A second secret key for downloads.
- Separate add-key and temporary download-token.
- Server-side concurrent download limits.
- Per-key rate limits.
- Clear server errors instead of crashes.

Recommended approach:

1. `/project_by_key` accepts the main key.
2. Server returns a temporary download token.
3. File downloads require that token.
4. Token has expiration and concurrency limits.

## v2.0.0 - Admin Client

Separate Windows admin client for server maintenance:

- Upload mods.
- Delete mods.
- Regenerate manifests.
- Manage keys.
- Update modpack version.
- Publish changelog.
- Restart service when configured.

Admin access must use separate authorization. The normal player key should not grant admin permissions.
