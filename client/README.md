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
