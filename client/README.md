# Flandosync Client

## Run From Source

```bash
python -m pip install -r requirements.txt
python client.py
```

Copy and edit settings:

```bash
cp flandosync_settings.example.json flandosync_settings.json
```

## Build Windows EXE

```powershell
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed --name FlandosyncLauncher client.py
```

The executable will be created in `dist/`.

Ship the executable together with a `flandosync_settings.json` file configured for your server.

## Client Features

- Right-click a modpack to rename or remove it.
- Right-click a modpack to change its local folder without adding it again.
- Renaming only changes the local display name. The server modpack name stays unchanged.
- Removing a modpack deletes it from the local list. Synced files are kept unless the confirmation checkbox is enabled.
- `Delete extra files` removes files in synced folders that are not present in the manifest.
- `Export logs` saves the console log and sync changes list to a text file.
- `Settings` lets users edit the server URL, select the theme, and test server connectivity.
- Manifest caching and limited parallel downloads are configurable in `Settings`.
