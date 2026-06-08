# Flandosync Server

## Configure

Copy the example config:

```bash
cp config.example.json config.json
```

Edit `config.json`:

```json
{
    "server_url": "http://your-host.example:8000",
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

`server_url` is a fallback URL. When clients connect through a domain, reverse proxy, or local IP, the server uses the incoming `Host` header to generate matching manifest links.

Download files require temporary tokens by default. The client gets a token from `/project_by_key`, and the server limits how many parallel downloads may use the same token.

The web admin panel is disabled by default. To enable it, set `admin_enabled` to `true` and set a strong `admin_token`, or provide the token through the `FLANDOSYNC_ADMIN_TOKEN` environment variable.

Keep `admin_host` as `127.0.0.1` unless you have a trusted private network or reverse proxy with HTTPS. A safe remote workflow is to keep the admin panel bound to localhost and access it through an SSH tunnel.

## Add a Modpack

Create a pack folder:

```bash
mkdir -p modpacks/example-pack/mods modpacks/example-pack/config
```

Put files in it, then generate the manifest:

```bash
python server.py -generate example-pack
```

You can set a visible modpack version and changelog:

```bash
python server.py -generate example-pack -version 1.2.0 -changelog "Added new mods"
```

For longer notes, put the text in a UTF-8 file:

```bash
python server.py -generate example-pack -version 1.2.0 -changelog-file changelog.txt
```

Start the HTTP server:

```bash
python server.py -serve
```

If `admin_enabled` is true, `-serve` starts both the public sync server and the admin web panel. You can also start only the admin panel:

```bash
python server.py -serve-admin
```

The first web admin version can list modpacks, show manifests, and regenerate manifests with version/changelog. It does not upload files, delete files, manage keys, or restart services.

## Files Not To Publish

Do not commit:

- `config.json`
- `keys.json`
- `modpacks/`
- generated `manifest.json`
- generated `key.txt`
