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
    "max_concurrent_downloads_per_token": 3
}
```

`server_url` is a fallback URL. When clients connect through a domain, reverse proxy, or local IP, the server uses the incoming `Host` header to generate matching manifest links.

Download files require temporary tokens by default. The client gets a token from `/project_by_key`, and the server limits how many parallel downloads may use the same token.

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

## Files Not To Publish

Do not commit:

- `config.json`
- `keys.json`
- `modpacks/`
- generated `manifest.json`
- generated `key.txt`
