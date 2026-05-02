import argparse
import hashlib
import json
import os
import secrets
import time
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse


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

    def generate_manifest(self, modpack_name):
        modpack_path = os.path.join(self.config["modpacks_dir"], modpack_name)
        if not os.path.exists(modpack_path):
            os.makedirs(os.path.join(modpack_path, "mods"), exist_ok=True)
            os.makedirs(os.path.join(modpack_path, "config"), exist_ok=True)
            print(f"Created modpack structure for {modpack_name}")

        manifest = {
            "name": modpack_name,
            "version": "1.0.0",
            "generated_at": int(time.time()),
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
        print(f"Key: {access_key}")
        print(f"Files: {len(manifest['files'])}")
        print("-" * 30)

    def serve(self):
        port = int(self.config["port"])
        server_address = ("", port)
        server_root = self.base_dir
        config_path = self.config_path

        class FlandoHandler(SimpleHTTPRequestHandler):
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

                base_url = self.external_base_url(server)
                for file_info in manifest.get("files", []):
                    file_url = file_info.get("url", "")
                    if file_url.startswith("/"):
                        file_info["url"] = base_url + file_url
                    elif not file_url.startswith(("http://", "https://")):
                        file_info["url"] = urljoin(base_url + "/", file_url)

                self.send_json(manifest)
                return True

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
                        manifest_url = (
                            f"{self.external_base_url(server)}/modpacks/{encoded_modpack}/manifest.json"
                        )
                        self.send_json({"manifest_url": manifest_url})
                    else:
                        body = b"Key not found"
                        self.send_response(404)
                        self.send_header("Content-Type", "text/plain; charset=utf-8")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                    return

                server = FlandosyncServer(config_path)
                if self.send_dynamic_manifest(server, request_path):
                    return

                return super().do_GET()

        handler = partial(FlandoHandler, directory=server_root)
        httpd = HTTPServer(server_address, handler)
        print(f"Flandosync server listening on port {port}")
        print(f"Serving root: {server_root}")
        httpd.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flandosync Server CLI")
    parser.add_argument("-generate", type=str, help="Generate a manifest for the named modpack")
    parser.add_argument("-serve", action="store_true", help="Start the HTTP server")

    args = parser.parse_args()
    server = FlandosyncServer()

    if args.generate:
        server.generate_manifest(args.generate)
    elif args.serve:
        server.serve()
    else:
        parser.print_help()
