# Flandosync Admin Client

The admin client is a separate PyQt desktop tool for maintaining a Flandosync server over SSH.

It does not expose a public admin HTTP API and does not use player access keys for admin work.

## Run From Source

```bash
python -m pip install -r requirements.txt
python admin_client.py
```

Copy and edit settings:

```bash
cp admin_settings.example.json admin_settings.json
```

## MVP Features

- Test SSH access.
- List server modpacks.
- Generate a manifest for one modpack.
- Set manifest version.
- Set a short changelog.
- Optionally restart a configured systemd service.

## Safety

The client runs narrow predefined commands only. It is not a remote terminal.

Recommended server-side setup:

- Use a dedicated SSH user.
- Limit that user to the Flandosync project directory where possible.
- Do not use player keys as admin credentials.
- Keep `admin_settings.json`, SSH keys, real hosts, and production paths out of public repositories.
