import argparse
import hashlib
import html
import json
import os
import secrets
import threading
import time
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlencode, unquote, urljoin, urlparse, urlunparse


class FlandosyncServer:
    def __init__(self, config_path="config.json"):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = self.resolve_path(config_path)
        self.keys_file = os.path.join(self.base_dir, "keys.json")
        self.load_config()
        self.load_keys()

    def resolve_path(self, path):
        if os.path.isabs(path):
            return path
        return os.path.abspath(os.path.join(self.base_dir, path))

    def load_config(self):
        default_config = {
            "server_url": "http://localhost:8000",
            "modpacks_dir": "./modpacks",
            "port": 8000,
            "require_download_token": True,
            "download_token_ttl_seconds": 3600,
            "max_concurrent_downloads_per_token": 3,
            "admin_enabled": False,
            "admin_host": "127.0.0.1",
            "admin_port": 8010,
            "admin_token": "",
        }

        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = {**default_config, **json.load(f)}
        else:
            self.config = default_config
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)

        self.config["server_url"] = self.config["server_url"].rstrip("/")
        self.config["modpacks_dir"] = self.resolve_path(self.config["modpacks_dir"])

    def load_keys(self):
        if os.path.exists(self.keys_file):
            with open(self.keys_file, "r", encoding="utf-8") as f:
                self.keys = json.load(f)
        else:
            self.keys = {}

    def save_keys(self):
        with open(self.keys_file, "w", encoding="utf-8") as f:
            json.dump(self.keys, f, ensure_ascii=False, indent=4)

    def get_file_hash(self, filepath):
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(1024 * 1024), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def get_or_create_access_key(self, modpack_name, modpack_path):
        key_path = os.path.join(modpack_path, "key.txt")

        if os.path.exists(key_path):
            with open(key_path, "r", encoding="utf-8") as f:
                key = f.read().strip()
            if key:
                self.keys[key] = modpack_name
                self.save_keys()
                return key

        for key, mapped_modpack in self.keys.items():
            if mapped_modpack == modpack_name:
                with open(key_path, "w", encoding="utf-8") as f:
                    f.write(key)
                return key

        key = secrets.token_hex(16)
        self.keys[key] = modpack_name
        self.save_keys()
        with open(key_path, "w", encoding="utf-8") as f:
            f.write(key)
        return key

    def load_existing_manifest(self, modpack_path):
        manifest_path = os.path.join(modpack_path, "manifest.json")
        if not os.path.exists(manifest_path):
            return {}

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def generate_manifest(self, modpack_name, version=None, changelog=None):
        modpack_path = os.path.join(self.config["modpacks_dir"], modpack_name)
        if not os.path.exists(modpack_path):
            os.makedirs(os.path.join(modpack_path, "mods"), exist_ok=True)
            os.makedirs(os.path.join(modpack_path, "config"), exist_ok=True)
            print(f"Created modpack structure for {modpack_name}")

        existing_manifest = self.load_existing_manifest(modpack_path)
        manifest_version = version or existing_manifest.get("version") or "1.0.0"
        manifest_changelog = changelog
        if manifest_changelog is None:
            manifest_changelog = existing_manifest.get("changelog", "")

        manifest = {
            "name": modpack_name,
            "version": manifest_version,
            "generated_at": int(time.time()),
            "changelog": manifest_changelog,
            "files": [],
        }

        encoded_modpack = quote(modpack_name, safe="")
        for root, _, files in os.walk(modpack_path):
            for file_name in sorted(files):
                if file_name in {"manifest.json", "key.txt"}:
                    continue

                full_path = os.path.join(root, file_name)
                rel_path = os.path.relpath(full_path, modpack_path).replace("\\", "/")
                encoded_path = quote(rel_path, safe="/")

                manifest["files"].append(
                    {
                        "path": rel_path,
                        "size": os.path.getsize(full_path),
                        "sha256": self.get_file_hash(full_path),
                        "url": f"/modpacks/{encoded_modpack}/{encoded_path}",
                    }
                )

        manifest_path = os.path.join(modpack_path, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=4)

        access_key = self.get_or_create_access_key(modpack_name, modpack_path)

        print("-" * 30)
        print("flandosync")
        print("Manifest generated successfully")
        print(f"Path: {manifest_path}")
        print(f"Version: {manifest_version}")
        print(f"Key: {access_key}")
        print(f"Files: {len(manifest['files'])}")
        print("-" * 30)

    def list_modpacks(self):
        if not os.path.isdir(self.config["modpacks_dir"]):
            return []

        modpacks = []
        for name in sorted(os.listdir(self.config["modpacks_dir"])):
            modpack_path = os.path.join(self.config["modpacks_dir"], name)
            if not os.path.isdir(modpack_path):
                continue

            manifest = self.load_existing_manifest(modpack_path)
            modpacks.append(
                {
                    "name": name,
                    "version": manifest.get("version", ""),
                    "generated_at": manifest.get("generated_at", 0),
                    "files": len(manifest.get("files", [])),
                    "has_manifest": bool(manifest),
                }
            )
        return modpacks

    def safe_modpack_name(self, modpack_name):
        if not modpack_name or "/" in modpack_name or "\\" in modpack_name:
            raise ValueError("Invalid modpack name")
        modpack_path = os.path.abspath(os.path.join(self.config["modpacks_dir"], modpack_name))
        modpacks_root = os.path.abspath(self.config["modpacks_dir"])
        if os.path.commonpath([modpacks_root, modpack_path]) != modpacks_root:
            raise ValueError("Invalid modpack path")
        return modpack_name

    def serve(self):
        port = int(self.config["port"])
        server_address = ("", port)
        server_root = self.base_dir
        config_path = self.config_path

        class FlandoHandler(SimpleHTTPRequestHandler):
            download_tokens = {}
            token_lock = threading.Lock()

            def external_base_url(self, server):
                host = self.headers.get("Host")
                if host:
                    scheme = self.headers.get("X-Forwarded-Proto")
                    if not scheme:
                        scheme = urlparse(server.config["server_url"]).scheme or "http"
                    return f"{scheme}://{host}".rstrip("/")
                return server.config["server_url"]

            def send_json(self, body_obj, status=200):
                body = json.dumps(body_obj, ensure_ascii=False, indent=4).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def send_text(self, body_text, status=200):
                body = body_text.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def config_bool(self, server, key):
                value = server.config.get(key)
                if isinstance(value, bool):
                    return value
                return str(value).strip().lower() in {"1", "true", "yes", "on"}

            def cleanup_tokens(self):
                now = time.time()
                with self.token_lock:
                    expired = [
                        token for token, data in self.download_tokens.items()
                        if data["expires_at"] <= now and data["active"] <= 0
                    ]
                    for token in expired:
                        self.download_tokens.pop(token, None)

            def create_download_token(self, server, modpack):
                ttl = int(server.config.get("download_token_ttl_seconds", 3600))
                token = secrets.token_urlsafe(32)
                expires_at = int(time.time() + ttl)
                self.cleanup_tokens()
                with self.token_lock:
                    self.download_tokens[token] = {
                        "modpack": modpack,
                        "expires_at": expires_at,
                        "active": 0,
                    }
                return token, expires_at

            def token_for_request(self, query):
                query_token = query.get("download_token", query.get("token", [None]))[0]
                if query_token:
                    return query_token

                auth_header = self.headers.get("Authorization", "")
                if auth_header.lower().startswith("bearer "):
                    return auth_header.split(" ", 1)[1].strip()

                return self.headers.get("X-Flandosync-Token")

            def validate_download_token(self, server, modpack, token):
                if not self.config_bool(server, "require_download_token"):
                    return True, None
                if not token:
                    return False, (HTTPStatus.UNAUTHORIZED, "Missing download token")

                now = time.time()
                max_active = int(server.config.get("max_concurrent_downloads_per_token", 3))
                with self.token_lock:
                    token_data = self.download_tokens.get(token)
                    if not token_data:
                        return False, (HTTPStatus.UNAUTHORIZED, "Invalid download token")
                    if token_data["expires_at"] <= now:
                        if token_data["active"] <= 0:
                            self.download_tokens.pop(token, None)
                        return False, (HTTPStatus.UNAUTHORIZED, "Expired download token")
                    if token_data["modpack"] != modpack:
                        return False, (HTTPStatus.FORBIDDEN, "Download token is for a different modpack")
                    if token_data["active"] >= max_active:
                        return False, (HTTPStatus.TOO_MANY_REQUESTS, "Too many active downloads for this token")
                    token_data["active"] += 1
                return True, None

            def release_download_token(self, token):
                if not token:
                    return
                with self.token_lock:
                    token_data = self.download_tokens.get(token)
                    if token_data:
                        token_data["active"] = max(0, token_data["active"] - 1)

            def add_query_param(self, url, key, value):
                parsed = urlparse(url)
                query = parse_qs(parsed.query)
                query[key] = [value]
                return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))

            def send_dynamic_manifest(self, server, request_path):
                parts = request_path.strip("/").split("/")
                if len(parts) != 3 or parts[0] != "modpacks" or parts[2] != "manifest.json":
                    return False

                modpack = unquote(parts[1])
                manifest_path = os.path.abspath(
                    os.path.join(server.config["modpacks_dir"], modpack, "manifest.json")
                )
                modpacks_root = os.path.abspath(server.config["modpacks_dir"])
                if os.path.commonpath([modpacks_root, manifest_path]) != modpacks_root:
                    return False
                if not os.path.exists(manifest_path):
                    return False

                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)

                query = parse_qs(urlparse(self.path).query)
                download_token = self.token_for_request(query)
                base_url = self.external_base_url(server)
                for file_info in manifest.get("files", []):
                    file_url = file_info.get("url", "")
                    if file_url.startswith("/"):
                        file_info["url"] = base_url + file_url
                    elif not file_url.startswith(("http://", "https://")):
                        file_info["url"] = urljoin(base_url + "/", file_url)
                    if download_token:
                        file_info["url"] = self.add_query_param(
                            file_info["url"], "download_token", download_token
                        )

                self.send_json(manifest)
                return True

            def modpack_download_parts(self, request_path):
                parts = request_path.strip("/").split("/")
                if len(parts) < 3 or parts[0] != "modpacks":
                    return None
                modpack = unquote(parts[1])
                rel_path = "/".join(parts[2:])
                if rel_path in {"manifest.json", "key.txt"}:
                    return None
                return modpack, rel_path

            def is_allowed_public_file(self, request_path):
                if request_path in {"", "/"}:
                    return False
                parts = request_path.strip("/").split("/")
                return len(parts) == 3 and parts[0] == "modpacks" and parts[2] == "manifest.json"

            def do_GET(self):
                parsed_url = urlparse(self.path)
                request_path = parsed_url.path

                if request_path == "/project_by_key":
                    query = parse_qs(parsed_url.query)
                    key = query.get("key", [None])[0]

                    server = FlandosyncServer(config_path)
                    if key in server.keys:
                        modpack = server.keys[key]
                        encoded_modpack = quote(modpack, safe="")
                        token, expires_at = self.create_download_token(server, modpack)
                        manifest_url = (
                            f"{self.external_base_url(server)}/modpacks/{encoded_modpack}/manifest.json"
                        )
                        self.send_json(
                            {
                                "manifest_url": manifest_url,
                                "manifest_url_with_token": self.add_query_param(
                                    manifest_url, "download_token", token
                                ),
                                "download_token": token,
                                "download_token_expires_at": expires_at,
                            }
                        )
                    else:
                        self.send_text("Key not found", HTTPStatus.NOT_FOUND)
                    return

                server = FlandosyncServer(config_path)
                if self.send_dynamic_manifest(server, request_path):
                    return

                download_parts = self.modpack_download_parts(request_path)
                if not download_parts:
                    if self.is_allowed_public_file(request_path):
                        return super().do_GET()
                    self.send_text("Not found", HTTPStatus.NOT_FOUND)
                    return

                modpack, _ = download_parts
                query = parse_qs(parsed_url.query)
                token = self.token_for_request(query)
                is_valid, error = self.validate_download_token(server, modpack, token)
                if not is_valid:
                    status, message = error
                    self.send_text(message, status)
                    return

                try:
                    return super().do_GET()
                finally:
                    self.release_download_token(token)

        handler = partial(FlandoHandler, directory=server_root)
        httpd = ThreadingHTTPServer(server_address, handler)
        print(f"Flandosync server listening on port {port}")
        print(f"Serving root: {server_root}")
        self.start_admin_server_if_enabled()
        httpd.serve_forever()

    def start_admin_server_if_enabled(self):
        if not self.config_bool("admin_enabled"):
            return

        admin_token = self.admin_token()
        if not admin_token:
            print("Flandosync admin web is enabled, but admin_token is empty. Admin web was not started.")
            return

        thread = threading.Thread(target=self.serve_admin, daemon=True)
        thread.start()

    def config_bool(self, key):
        value = self.config.get(key)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def admin_token(self):
        return os.environ.get("FLANDOSYNC_ADMIN_TOKEN") or str(self.config.get("admin_token", "")).strip()

    def serve_admin(self):
        host = str(self.config.get("admin_host", "127.0.0.1"))
        port = int(self.config.get("admin_port", 8010))
        config_path = self.config_path

        class AdminHandler(SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                print(f"[admin] {self.address_string()} - {format % args}")

            def send_json(self, body_obj, status=200):
                body = json.dumps(body_obj, ensure_ascii=False, indent=4).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def send_html(self, body_text, status=200):
                body = body_text.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def request_token(self):
                auth_header = self.headers.get("Authorization", "")
                if auth_header.lower().startswith("bearer "):
                    return auth_header.split(" ", 1)[1].strip()
                return self.headers.get("X-Flandosync-Admin-Token", "")

            def require_admin(self, server):
                expected = server.admin_token()
                actual = self.request_token()
                if expected and actual and secrets.compare_digest(expected, actual):
                    return True
                self.send_json({"error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return False

            def read_json_body(self):
                try:
                    content_length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    content_length = 0
                if content_length > 64 * 1024:
                    raise ValueError("Request body is too large")
                raw_body = self.rfile.read(content_length) if content_length else b"{}"
                return json.loads(raw_body.decode("utf-8"))

            def admin_page(self):
                return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Flandosync Admin</title>
  <style>
    :root { color-scheme: dark light; font-family: Segoe UI, sans-serif; }
    body { margin: 0; background: #171a1f; color: #edf1f7; }
    main { max-width: 1080px; margin: 0 auto; padding: 24px; }
    header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
    h1 { font-size: 24px; margin: 0; }
    section { border-top: 1px solid #313844; padding: 18px 0; }
    label { display: block; margin: 10px 0 5px; color: #b7c0cd; }
    input, textarea, button { font: inherit; }
    input, textarea { width: 100%; box-sizing: border-box; padding: 9px; border-radius: 6px; border: 1px solid #485262; background: #101319; color: #edf1f7; }
    textarea { min-height: 96px; resize: vertical; }
    button { padding: 8px 12px; border-radius: 6px; border: 1px solid #5b6678; background: #2f6f4e; color: white; cursor: pointer; }
    button.secondary { background: #303846; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 8px; border-bottom: 1px solid #313844; }
    tr:hover { background: #202631; }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
    pre { white-space: pre-wrap; background: #101319; padding: 12px; border-radius: 6px; border: 1px solid #313844; min-height: 80px; }
    @media (max-width: 760px) { .grid { grid-template-columns: 1fr; } header { align-items: stretch; flex-direction: column; } }
  </style>
</head>
<body>
<main>
  <header>
    <h1>Flandosync Admin</h1>
    <button class="secondary" onclick="loadModpacks()">Refresh</button>
  </header>

  <section>
    <label for="token">Admin token</label>
    <input id="token" type="password" autocomplete="current-password">
    <div class="actions">
      <button onclick="saveToken()">Save token locally</button>
      <button class="secondary" onclick="loadStatus()">Test</button>
    </div>
  </section>

  <section>
    <h2>Modpacks</h2>
    <table>
      <thead><tr><th>Name</th><th>Version</th><th>Files</th><th>Manifest</th></tr></thead>
      <tbody id="modpacks"></tbody>
    </table>
  </section>

  <section>
    <h2>Generate manifest</h2>
    <div class="grid">
      <div>
        <label for="modpack">Modpack</label>
        <input id="modpack">
      </div>
      <div>
        <label for="version">Version</label>
        <input id="version" placeholder="1.2.3">
      </div>
    </div>
    <label for="changelog">Changelog</label>
    <textarea id="changelog"></textarea>
    <div class="actions">
      <button onclick="generateManifest()">Generate</button>
      <button class="secondary" onclick="loadManifest()">Show manifest</button>
    </div>
  </section>

  <section>
    <h2>Output</h2>
    <pre id="output"></pre>
  </section>
</main>
<script>
const tokenInput = document.getElementById('token');
const saved = sessionStorage.getItem('flandosync_admin_token');
if (saved) tokenInput.value = saved;

function saveToken() {
  sessionStorage.setItem('flandosync_admin_token', tokenInput.value);
  writeOutput('Token saved in this browser tab.');
}

function headers() {
  return {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer ' + tokenInput.value
  };
}

function writeOutput(value) {
  document.getElementById('output').textContent =
    typeof value === 'string' ? value : JSON.stringify(value, null, 2);
}

async function request(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { ...headers(), ...(options.headers || {}) } });
  const text = await response.text();
  let body;
  try { body = JSON.parse(text); } catch { body = text; }
  if (!response.ok) throw body;
  return body;
}

async function loadStatus() {
  try { writeOutput(await request('/api/status')); } catch (err) { writeOutput(err); }
}

async function loadModpacks() {
  try {
    const data = await request('/api/modpacks');
    const tbody = document.getElementById('modpacks');
    tbody.innerHTML = '';
    data.modpacks.forEach(pack => {
      const row = document.createElement('tr');
      row.innerHTML = `<td>${escapeHtml(pack.name)}</td><td>${escapeHtml(pack.version || '')}</td><td>${pack.files}</td><td>${pack.has_manifest ? 'yes' : 'no'}</td>`;
      row.onclick = () => {
        document.getElementById('modpack').value = pack.name;
        document.getElementById('version').value = pack.version || '';
      };
      tbody.appendChild(row);
    });
    writeOutput(data);
  } catch (err) { writeOutput(err); }
}

async function loadManifest() {
  const modpack = encodeURIComponent(document.getElementById('modpack').value);
  try { writeOutput(await request('/api/manifest?modpack=' + modpack)); } catch (err) { writeOutput(err); }
}

async function generateManifest() {
  const payload = {
    modpack: document.getElementById('modpack').value,
    version: document.getElementById('version').value,
    changelog: document.getElementById('changelog').value
  };
  try {
    writeOutput(await request('/api/generate', { method: 'POST', body: JSON.stringify(payload) }));
    await loadModpacks();
  } catch (err) { writeOutput(err); }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[ch]));
}
</script>
</body>
</html>"""

            def do_GET(self):
                parsed_url = urlparse(self.path)
                server = FlandosyncServer(config_path)

                if parsed_url.path == "/":
                    self.send_html(self.admin_page())
                    return

                if not self.require_admin(server):
                    return

                if parsed_url.path == "/api/status":
                    self.send_json(
                        {
                            "ok": True,
                            "modpacks_dir": server.config["modpacks_dir"],
                            "modpacks": len(server.list_modpacks()),
                        }
                    )
                    return

                if parsed_url.path == "/api/modpacks":
                    self.send_json({"modpacks": server.list_modpacks()})
                    return

                if parsed_url.path == "/api/manifest":
                    query = parse_qs(parsed_url.query)
                    modpack = server.safe_modpack_name(query.get("modpack", [""])[0])
                    manifest = server.load_existing_manifest(
                        os.path.join(server.config["modpacks_dir"], modpack)
                    )
                    if not manifest:
                        self.send_json({"error": "Manifest not found"}, HTTPStatus.NOT_FOUND)
                        return
                    self.send_json(manifest)
                    return

                self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

            def do_POST(self):
                parsed_url = urlparse(self.path)
                server = FlandosyncServer(config_path)
                if not self.require_admin(server):
                    return

                if parsed_url.path == "/api/generate":
                    try:
                        payload = self.read_json_body()
                        modpack = server.safe_modpack_name(str(payload.get("modpack", "")).strip())
                        if modpack not in {item["name"] for item in server.list_modpacks()}:
                            self.send_json(
                                {"error": "Modpack does not exist. Create folders on the server first."},
                                HTTPStatus.BAD_REQUEST,
                            )
                            return
                        version = str(payload.get("version", "")).strip() or None
                        changelog = str(payload.get("changelog", "")).strip()
                        server.generate_manifest(modpack, version=version, changelog=changelog)
                        manifest = server.load_existing_manifest(
                            os.path.join(server.config["modpacks_dir"], modpack)
                        )
                        self.send_json({"ok": True, "manifest": manifest})
                    except Exception as exc:
                        self.send_json({"error": html.escape(str(exc))}, HTTPStatus.BAD_REQUEST)
                    return

                self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

        httpd = ThreadingHTTPServer((host, port), AdminHandler)
        print(f"Flandosync admin web listening on {host}:{port}")
        httpd.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flandosync Server CLI")
    parser.add_argument("-generate", type=str, help="Generate a manifest for the named modpack")
    parser.add_argument("-version", type=str, help="Set the modpack version written to manifest.json")
    parser.add_argument("-changelog", type=str, help="Set a short changelog written to manifest.json")
    parser.add_argument("-changelog-file", type=str, help="Read changelog text from a UTF-8 file")
    parser.add_argument("-serve", action="store_true", help="Start the HTTP server")
    parser.add_argument("-serve-admin", action="store_true", help="Start only the optional web admin server")

    args = parser.parse_args()
    server = FlandosyncServer()

    if args.generate:
        changelog = args.changelog
        if args.changelog_file:
            with open(args.changelog_file, "r", encoding="utf-8") as f:
                changelog = f.read().strip()
        server.generate_manifest(args.generate, version=args.version, changelog=changelog)
    elif args.serve_admin:
        server.serve_admin()
    elif args.serve:
        server.serve()
    else:
        parser.print_help()
