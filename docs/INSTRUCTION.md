# Flandosync Instructions

This document explains how to publish, configure, run, and maintain Flandosync.

Flandosync has two independent parts:

- Server: stores modpack files, generates manifests, keeps access keys, and serves files over HTTP.
- Client: desktop app for players. It accepts an access key, asks for the Minecraft instance folder, and syncs files from the server.

## Repository Layout

```text
flandosync-public/
  client/
    client.py
    flandosync_settings.example.json
    requirements.txt
    README.md
  server/
    server.py
    config.example.json
    requirements.txt
    README.md
  docs/
    INSTRUCTION.md
  .gitignore
  README.md
```

Runtime files are intentionally ignored by Git:

```text
server/config.json
server/keys.json
server/modpacks/
client/flandosync_settings.json
client/flandosync_client.json
```

Do not publish real keys, private modpack files, IP addresses, domains, or player-specific paths.

## Server Setup

Install Python 3.10 or newer.

Copy the example config:

```bash
cd server
cp config.example.json config.json
```

Edit `config.json`:

```json
{
    "server_url": "http://localhost:8000",
    "modpacks_dir": "./modpacks",
    "port": 8000,
    "require_download_token": true,
    "download_token_ttl_seconds": 3600,
    "max_concurrent_downloads_per_token": 3,
    "admin_enabled": false,
    "admin_host": "127.0.0.1",
    "admin_port": 8010,
    "admin_token": ""
}
```

Fields:

- `server_url`: fallback URL used when the HTTP request does not include a `Host` header.
- `modpacks_dir`: folder where modpack folders live.
- `port`: HTTP port to listen on.
- `require_download_token`: require temporary tokens for file downloads.
- `download_token_ttl_seconds`: token lifetime after `/project_by_key`.
- `max_concurrent_downloads_per_token`: parallel file downloads allowed for one token.
- `admin_enabled`: starts the optional web admin panel when `-serve` is running.
- `admin_host`: address for the web admin panel. Keep `127.0.0.1` for safest use.
- `admin_port`: port for the web admin panel.
- `admin_token`: admin token for web admin API calls. You can also use `FLANDOSYNC_ADMIN_TOKEN`.

The server also supports both LAN and public access. When a client connects through a LAN IP, the server returns LAN links. When a client connects through a domain, the server returns domain links. This is based on the incoming HTTP `Host` header.

By default, modpack files cannot be downloaded directly without a temporary token. The client requests this token automatically when the player adds a modpack or starts sync.

The web admin panel is disabled by default. The safest remote access pattern is:

```bash
ssh -L 8010:127.0.0.1:8010 user@your-server
```

Then open `http://127.0.0.1:8010` on your local computer and enter the admin token in the page.

## Creating a Modpack

Create a modpack folder:

```bash
mkdir -p modpacks/example-pack/mods
mkdir -p modpacks/example-pack/config
```

Put files inside the modpack folder:

```text
modpacks/example-pack/mods/some-mod.jar
modpacks/example-pack/config/some-config.toml
```

Generate the manifest:

```bash
python server.py -generate example-pack
```

Optionally set a version and changelog:

```bash
python server.py -generate example-pack -version 1.2.0 -changelog "Added new mods"
```

For longer changelogs:

```bash
python server.py -generate example-pack -version 1.2.0 -changelog-file changelog.txt
```

The command creates or updates:

```text
modpacks/example-pack/manifest.json
modpacks/example-pack/key.txt
keys.json
```

The access key is printed in the terminal. Give this key to players.

## Updating a Modpack

When you add, remove, or replace files, regenerate the manifest:

```bash
cd server
python server.py -generate example-pack -version 1.2.1 -changelog "Updated mods"
```

Players do not need a new client. They only need to press `SYNC` again.
The client warns players when the server version differs from their last synced version and shows the changelog when it is present.

The generated key stays stable. It is reused from `key.txt` or `keys.json`.

## Starting the Server

Run:

```bash
cd server
python server.py -serve
```

If `admin_enabled` is true, the command also starts the web admin panel. To run only the admin panel:

```bash
python server.py -serve-admin
```

Useful URLs:

```text
http://localhost:8000/project_by_key?key=<ACCESS_KEY>
http://localhost:8000/modpacks/example-pack/manifest.json
```

For a real deployment, run the server behind a process manager such as systemd, tmux, screen, Docker, or another service manager.

## Client Setup

Install dependencies:

```bash
cd client
python -m pip install -r requirements.txt
```

Copy the example settings:

```bash
cp flandosync_settings.example.json flandosync_settings.json
```

Edit `flandosync_settings.json`:

```json
{
    "server_url": "http://your-server.example:8000",
    "app_name": "Flandosync Client",
    "theme": "dark"
}
```

Run:

```bash
python client.py
```

## Client Settings

Click `Settings` in the client to edit:

- server URL;
- theme.
- manifest cache TTL;
- download worker count;
- request timeout.

The settings dialog also has a `Test server` button. It checks whether the configured Flandosync server is reachable.

Settings are stored in:

```text
flandosync_settings.json
```

`manifest_cache_ttl_seconds` controls how long the client may reuse a recently downloaded manifest. Set it to `0` to disable manifest caching.

`download_workers` controls parallel downloads. Keep it low for small private servers. The recommended range is `2-4`.

`request_timeout_seconds` controls HTTP request timeout.

## Using the Client

1. Enter the access key.
2. Click `Add modpack`.
3. Choose the root folder of the Minecraft instance.
4. Select the modpack in the list.
5. Click `SYNC`.

Choose the instance root folder, not the `mods` folder.

Correct:

```text
C:\Users\<name>\AppData\Roaming\.minecraft
```

Incorrect:

```text
C:\Users\<name>\AppData\Roaming\.minecraft\mods
```

The manifest contains paths like `mods/example.jar`, so choosing `mods` directly would create `mods/mods/example.jar`.

## Managing Saved Modpacks

Right-click a modpack in the list to open the context menu.

Available actions:

- `Rename`: sets a local display alias.
- `Remove`: removes the modpack from the local list.

Renaming does not change the server modpack name. If the server name is `aerocraft` and the local alias is `My Pack`, the client displays:

```text
My Pack (aerocraft)
```

Removing a modpack keeps local files by default. The confirmation dialog has an optional checkbox:

```text
Also permanently delete synced files
```

When enabled, the client fetches the latest manifest and deletes only files listed in that manifest. It does not delete the whole selected Minecraft folder.

## Delete Extra Files Option

The client has a `Delete extra files` checkbox.

When disabled:

- files from the manifest are downloaded or updated;
- local-only client mods remain untouched.

When enabled:

- files from the manifest are downloaded or updated;
- files inside synced roots, such as `mods/` and `config/`, are deleted if they are not in the manifest.

Use this option only when you want a clean client folder matching the server pack.

## Logs And Sync Changes

The client shows a separate sync changes list for:

- downloaded files;
- skipped files;
- deleted files.

Use `Export logs` to save the console output and the sync changes list to a text file.

## Building a Windows EXE

Install build dependencies:

```powershell
cd client
python -m pip install -r requirements.txt pyinstaller
```

Build:

```powershell
python -m PyInstaller --noconfirm --clean --onefile --windowed --name FlandosyncLauncher client.py
```

The result will be:

```text
client/dist/FlandosyncLauncher.exe
```

Ship the executable together with:

```text
flandosync_settings.json
```

Do not ship `flandosync_client.json` unless you intentionally want to include saved local projects.

## Recommended Release Package

For players, include:

```text
FlandosyncLauncher.exe
flandosync_settings.json
README.txt
```

The player README should include:

- the access key;
- the correct server URL if needed;
- a reminder to choose the Minecraft instance root folder;
- a warning about `Delete extra files`.

## Safety Checklist Before Publishing

Before pushing to GitHub, verify that these are not present:

```text
keys.json
key.txt
manifest.json
modpacks/
flandosync_client.json
real config.json
real flandosync_settings.json
IP addresses
private domains
usernames
local filesystem paths
```

Commit only:

```text
config.example.json
flandosync_settings.example.json
source files
requirements
docs
```

## Common Maintenance Commands

Generate or update a modpack:

```bash
python server.py -generate example-pack
```

Start server:

```bash
python server.py -serve
```

Test key lookup:

```bash
curl "http://localhost:8000/project_by_key?key=<ACCESS_KEY>"
```

Test manifest:

```bash
curl "http://localhost:8000/modpacks/example-pack/manifest.json"
```

## Troubleshooting

If the client says the server is unavailable:

- check that `python server.py -serve` is running;
- check that the port in `config.json` is open;
- check that `flandosync_settings.json` points to the correct server URL;
- test `/project_by_key?key=<ACCESS_KEY>` in a browser.

If the client downloads nothing:

- regenerate the manifest;
- open `manifest.json` and check that `files` is not empty;
- make sure files are inside the selected modpack folder before running `-generate`.
- if manifest caching is enabled, wait for the cache TTL or set `manifest_cache_ttl_seconds` to `0`.

If files appear under `mods/mods`:

- the user selected the `mods` folder instead of the Minecraft instance root;
- remove the wrongly created folder and add the modpack again with the correct root.

If extra client mods are being removed:

- disable `Delete extra files`;
- only enable it when you want strict cleanup.
