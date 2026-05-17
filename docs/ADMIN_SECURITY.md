# Admin Panel Security

This document is the security plan for the future admin client and admin API.

## Main Rule

Player access keys must never grant admin permissions.

The player key is only for joining a modpack and downloading files. The admin client needs a separate authentication path with stronger controls.

## Recommended Design

Use SSH first if the server is managed by one trusted owner.

- The admin client connects over SSH.
- The server does not expose public admin HTTP endpoints.
- The SSH user should be limited to the Flandosync directory and service commands where possible.
- The admin client uploads files, regenerates manifests, rotates keys, and restarts the service through explicit commands.

Add an admin API only when SSH becomes too inconvenient.

## If An Admin API Is Added

The admin API should have all of these controls before it is exposed:

- Separate admin token or login, never the player key.
- HTTPS only when reachable from the internet.
- Tokens stored outside the public repository.
- Short-lived sessions or signed requests.
- Rate limits for login and write actions.
- Audit log for uploads, deletes, manifest generation, key creation, and service restarts.
- File upload size limits.
- Strict path validation so uploaded files cannot escape the modpack directory.
- Dry-run mode for destructive actions.
- Confirmation prompts for deleting files, rotating keys, and restarting services.

## Safer Admin Operations

Admin actions should be narrow and explicit:

- Upload mod files to a selected modpack.
- Delete only files inside the selected modpack.
- Regenerate one manifest at a time.
- Rotate one key at a time.
- Restart only the configured Flandosync service.

Avoid a generic remote terminal in the admin client. It is powerful, but it turns the app into a much larger security risk.

## Backups

Before destructive admin actions, create a timestamped backup of:

- `server.py`
- server config files
- key files
- the selected modpack manifest
- any files that will be deleted or overwritten

Backups should live outside the public web root.

## Access Limits For Players

Player downloads should eventually move from a permanent shared key to a short-lived download token:

1. The client sends the player key to `/project_by_key`.
2. The server returns manifest metadata and a temporary download token.
3. File downloads require that temporary token.
4. The token has expiration, rate limits, and concurrent download limits.

This helps protect the server when someone leaves a client stuck in a download loop.

## Do Not Commit

Never commit these values to GitHub:

- real player keys
- admin tokens
- SSH keys
- public IP addresses
- private domains
- live server paths
- production configs
