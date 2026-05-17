# Flandosync

Languages: [English](README.md) | [Русский](README_RU.md)

Flandosync is a small Minecraft modpack sync tool.

It has two parts:

- `server/` generates modpack manifests and serves files over HTTP.
- `client/` is a PyQt desktop launcher that downloads files listed in a manifest.

## Quick Start

Full setup and maintenance docs:

- English: [docs/INSTRUCTION.md](docs/INSTRUCTION.md)
- Russian: [docs/INSTRUCTION_RU.md](docs/INSTRUCTION_RU.md)

Roadmap:

- English: [docs/ROADMAP.md](docs/ROADMAP.md)
- Russian: [docs/ROADMAP_RU.md](docs/ROADMAP_RU.md)

Admin security planning:

- English: [docs/ADMIN_SECURITY.md](docs/ADMIN_SECURITY.md)
- Russian: [docs/ADMIN_SECURITY_RU.md](docs/ADMIN_SECURITY_RU.md)

Release history: [CHANGELOG.md](CHANGELOG.md)

### Server

```bash
cd server
cp config.example.json config.json
python server.py -generate example-pack
python server.py -serve
```

Put modpack files under:

```text
server/modpacks/<pack-name>/
```

For example:

```text
server/modpacks/example-pack/mods/example.jar
server/modpacks/example-pack/config/example.toml
```

After adding, removing, or changing files, regenerate the manifest:

```bash
python server.py -generate example-pack -version 1.2.1 -changelog "Updated mods"
```

The generated access key is printed in the terminal and saved in `key.txt`.
Clients warn players when the server version changes.

### Client

```bash
cd client
cp flandosync_settings.example.json flandosync_settings.json
python client.py
```

Enter the access key, choose the root Minecraft instance folder, then sync.

Choose the instance root folder, not the `mods` folder. For example:

```text
C:\Users\<you>\AppData\Roaming\.minecraft
```

## Cleaning Extra Files

The client has an optional checkbox to delete extra files.

When enabled, it removes files inside synced manifest roots such as `mods/` or `config/` that are not present in the manifest. When disabled, local-only client mods are left untouched.

## Security Notes

Flandosync access keys are simple shared tokens. Do not publish your real `keys.json`, generated `key.txt`, private modpack files, IP addresses, or domain-specific configs.

File downloads use temporary download tokens by default. The player access key is used to request a short-lived token, and the server limits concurrent downloads per token.

For public GitHub repositories, commit only the example configs.
