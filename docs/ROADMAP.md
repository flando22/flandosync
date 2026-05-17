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
- Change the local modpack folder without removing the modpack. Done.
- Better sync result summary. Done.
  - Downloaded files.
  - Skipped files.
  - Deleted extra files.
- Basic UX pass. In progress.

## v1.2.0 - Client Settings

- Settings dialog. Done.
- Server URL setting. Done.
- Theme selector. Done.
- Save settings to `flandosync_settings.json`. Done.
- Test server connection from the settings dialog. Done.
- Prevent long test errors from stretching the dialog. Done.

## v1.3.0 - Stability And Performance

- Manifest cache. Done.
- Limited parallel downloads. Done.
- Better timeouts and retries. Done.
- Safer behavior when the network fails. In progress.

## v1.4.0 - Modpack Versioning

- Add modpack version to the manifest. Done.
- Store the last synced version on the client. Done.
- Warn users when an update is available. Done.
- Show changelog when available. Done.

## v1.5.0 - Access Limits

Possible approaches:

- A second secret key for downloads. Replaced by temporary download tokens.
- Separate add-key and temporary download-token. Done.
- Server-side concurrent download limits. Done.
- Per-key rate limits. Partially done through per-token limits.
- Clear server errors instead of crashes. Done.

Recommended approach:

1. `/project_by_key` accepts the main key. Done.
2. Server returns a temporary download token. Done.
3. File downloads require that token. Done by default.
4. Token has expiration and concurrency limits. Done.

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

Detailed notes: [Admin Security](ADMIN_SECURITY.md).
