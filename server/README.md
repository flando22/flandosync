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
    "port": 8000
}
```

`server_url` is a fallback URL. When clients connect through a domain, reverse proxy, or local IP, the server uses the incoming `Host` header to generate matching manifest links.

## Add a Modpack

Create a pack folder:

```bash
mkdir -p modpacks/example-pack/mods modpacks/example-pack/config
```

Put files in it, then generate the manifest:

```bash
python server.py -generate example-pack
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
