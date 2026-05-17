import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


DEFAULT_CONFIG = {
    "server_url": "http://localhost:8000",
    "app_name": "Flandosync Client",
    "theme": "dark",
    "manifest_cache_ttl_seconds": 60,
    "download_workers": 3,
    "request_timeout_seconds": 30,
}


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def normalize_url(url):
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url.rstrip("/")


def load_external_config():
    config_path = os.path.join(app_dir(), "flandosync_settings.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except (OSError, json.JSONDecodeError):
            return DEFAULT_CONFIG

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=4)
    except OSError:
        pass
    return DEFAULT_CONFIG


def save_external_config(config):
    config_path = os.path.join(app_dir(), "flandosync_settings.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)


def bounded_int(value, default, minimum, maximum):
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default


def manifest_cache_path(manifest_url):
    cache_dir = os.path.join(app_dir(), "manifest_cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache_name = hashlib.sha256(manifest_url.encode("utf-8")).hexdigest() + ".json"
    return os.path.join(cache_dir, cache_name)


def add_query_param(url, key, value):
    if not value:
        return url
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query[key] = [value]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def auth_headers(download_token):
    if not download_token:
        return {}
    return {
        "Authorization": f"Bearer {download_token}",
        "X-Flandosync-Token": download_token,
    }


def strip_query_param(url, key):
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query.pop(key, None)
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


class SyncWorker(QThread):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    result = pyqtSignal(str, str)
    manifest_loaded = pyqtSignal(dict)
    finished = pyqtSignal(bool)

    def __init__(self, project_path, manifest_url, delete_extra=False, settings=None, download_token=None):
        super().__init__()
        self.project_path = project_path
        self.manifest_url = manifest_url
        self.delete_extra = delete_extra
        self.download_token = download_token
        self.settings = {**DEFAULT_CONFIG, **(settings or {})}
        self.timeout = bounded_int(self.settings.get("request_timeout_seconds"), 30, 5, 300)
        self.download_workers = bounded_int(self.settings.get("download_workers"), 3, 1, 8)
        self.manifest_cache_ttl = bounded_int(
            self.settings.get("manifest_cache_ttl_seconds"), 60, 0, 86400
        )

    def get_file_hash(self, filepath):
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(1024 * 1024), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def safe_local_path(self, rel_path):
        local_path = os.path.abspath(os.path.join(self.project_path, rel_path))
        project_root = os.path.abspath(self.project_path)
        if os.path.commonpath([project_root, local_path]) != project_root:
            raise ValueError(f"Unsafe path in manifest: {rel_path}")
        return local_path

    def request_with_retries(self, method, url, **kwargs):
        last_error = None
        headers = {**auth_headers(self.download_token), **kwargs.pop("headers", {})}
        for attempt in range(3):
            try:
                response = requests.request(method, url, timeout=self.timeout, headers=headers, **kwargs)
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
        raise last_error

    def load_manifest(self, manifest_url):
        cache_key_url = strip_query_param(manifest_url, "download_token")
        if self.download_token and "download_token" not in parse_qs(urlparse(manifest_url).query):
            manifest_url = add_query_param(manifest_url, "download_token", self.download_token)
        cache_path = manifest_cache_path(cache_key_url)
        if self.manifest_cache_ttl > 0 and os.path.exists(cache_path):
            age = time.time() - os.path.getmtime(cache_path)
            if age <= self.manifest_cache_ttl:
                with open(cache_path, "r", encoding="utf-8") as f:
                    self.log.emit(f"Using cached manifest ({int(age)}s old).")
                    return json.load(f)

        response = self.request_with_retries("GET", manifest_url)
        manifest = response.json()
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=4)
        return manifest

    def download_file(self, download_url, local_path, expected_hash):
        response = self.request_with_retries("GET", download_url, stream=True)

        tmp_path = local_path + ".flandosync_tmp"
        with open(tmp_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

        actual_hash = self.get_file_hash(tmp_path)
        if actual_hash != expected_hash:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise ValueError(f"Hash mismatch for {os.path.basename(local_path)}")

        os.replace(tmp_path, local_path)

    def delete_files_not_in_manifest(self, expected_paths, sync_roots):
        deleted = 0
        for root_name in sorted(sync_roots):
            root_path = self.safe_local_path(root_name)
            if not os.path.isdir(root_path):
                continue

            for current_root, dirs, files in os.walk(root_path, topdown=False):
                for file_name in files:
                    local_path = os.path.abspath(os.path.join(current_root, file_name))
                    if local_path.endswith(".flandosync_tmp"):
                        continue
                    if os.path.normcase(local_path) not in expected_paths:
                        os.remove(local_path)
                        deleted += 1
                        rel_path = os.path.relpath(local_path, self.project_path).replace("\\", "/")
                        self.log.emit(f"Deleted extra file: {rel_path}")
                        self.result.emit("Deleted", rel_path)

                for dir_name in dirs:
                    dir_path = os.path.join(current_root, dir_name)
                    try:
                        os.rmdir(dir_path)
                    except OSError:
                        pass

        self.log.emit(f"Cleanup finished. Deleted extra files: {deleted}")

    def sync_one_file(self, manifest_url, file_info):
        rel_path = file_info["path"]
        remote_hash = file_info["sha256"]
        download_url = urljoin(manifest_url, file_info["url"])
        if self.download_token and "download_token" not in parse_qs(urlparse(download_url).query):
            download_url = add_query_param(download_url, "download_token", self.download_token)
        local_path = self.safe_local_path(rel_path)

        os.makedirs(os.path.dirname(local_path), exist_ok=True)

        if os.path.exists(local_path):
            local_hash = self.get_file_hash(local_path)
            if local_hash == remote_hash:
                return "Skipped", rel_path, local_path

        self.download_file(download_url, local_path, remote_hash)
        return "Downloaded", rel_path, local_path

    def run(self):
        try:
            self.log.emit("Loading manifest...")
            manifest_url = normalize_url(self.manifest_url)
            manifest = self.load_manifest(manifest_url)
            self.manifest_loaded.emit(manifest)

            files = manifest.get("files", [])
            total_files = len(files)

            if total_files == 0:
                self.progress.emit(100)
                self.log.emit("Manifest is empty. Nothing to sync.")
                self.finished.emit(True)
                return

            os.makedirs(self.project_path, exist_ok=True)
            expected_paths = set()
            sync_roots = set()
            for file_info in files:
                rel_path = file_info["path"]
                local_path = self.safe_local_path(rel_path)
                expected_paths.add(os.path.normcase(local_path))
                sync_roots.add(rel_path.replace("\\", "/").split("/", 1)[0])

            completed = 0
            self.log.emit(f"Syncing {total_files} files with {self.download_workers} worker(s)...")
            with ThreadPoolExecutor(max_workers=self.download_workers) as executor:
                futures = [executor.submit(self.sync_one_file, manifest_url, file_info) for file_info in files]
                for future in as_completed(futures):
                    kind, rel_path, _ = future.result()
                    if kind == "Skipped":
                        self.log.emit(f"Skipped: {rel_path} is already up to date")
                    else:
                        self.log.emit(f"Downloaded: {rel_path}")
                    self.result.emit(kind, rel_path)
                    completed += 1
                    self.progress.emit(int((completed / total_files) * 100))

            if self.delete_extra:
                self.log.emit("Deleting files that are not in the manifest...")
                self.delete_files_not_in_manifest(expected_paths, sync_roots)

            self.log.emit("Sync completed successfully.")
            self.finished.emit(True)
        except Exception as exc:
            self.log.emit(f"ERROR: {exc}")
            self.finished.emit(False)


class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.config = dict(config)
        self.server_url_input = QLineEdit(normalize_url(self.config.get("server_url", DEFAULT_CONFIG["server_url"])))
        self.theme_input = QComboBox()
        self.theme_input.addItem("Dark", "dark")
        self.theme_input.addItem("Light", "light")
        current_theme = str(self.config.get("theme", DEFAULT_CONFIG["theme"])).lower()
        index = self.theme_input.findData(current_theme)
        self.theme_input.setCurrentIndex(index if index >= 0 else 0)
        self.cache_ttl_input = QLineEdit(str(self.config.get("manifest_cache_ttl_seconds", 60)))
        self.workers_input = QLineEdit(str(self.config.get("download_workers", 3)))
        self.timeout_input = QLineEdit(str(self.config.get("request_timeout_seconds", 30)))
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setMaximumWidth(520)
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        form_layout.addRow("Server URL:", self.server_url_input)
        form_layout.addRow("Theme:", self.theme_input)
        form_layout.addRow("Manifest cache TTL seconds:", self.cache_ttl_input)
        form_layout.addRow("Download workers:", self.workers_input)
        form_layout.addRow("Request timeout seconds:", self.timeout_input)
        layout.addLayout(form_layout)

        test_btn = QPushButton("Test server")
        test_btn.clicked.connect(self.test_server)
        layout.addWidget(test_btn)
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_config(self):
        config = {**DEFAULT_CONFIG, **self.config}
        config["server_url"] = normalize_url(self.server_url_input.text())
        config["theme"] = self.theme_input.currentData() or DEFAULT_CONFIG["theme"]
        config["manifest_cache_ttl_seconds"] = bounded_int(self.cache_ttl_input.text(), 60, 0, 86400)
        config["download_workers"] = bounded_int(self.workers_input.text(), 3, 1, 8)
        config["request_timeout_seconds"] = bounded_int(self.timeout_input.text(), 30, 5, 300)
        return config

    def test_server(self):
        try:
            server_url = normalize_url(self.server_url_input.text())
            timeout = bounded_int(self.timeout_input.text(), 30, 5, 300)
            response = requests.get(f"{server_url}/project_by_key", params={"key": "__healthcheck__"}, timeout=timeout)
            if response.status_code in {200, 404}:
                self.status_label.setText("Server is reachable.")
                self.status_label.setToolTip("")
            else:
                self.status_label.setText(f"Server answered with HTTP {response.status_code}.")
                self.status_label.setToolTip(response.text[:1000])
        except Exception as exc:
            self.status_label.setText("Could not reach server. Hover this message for details.")
            self.status_label.setToolTip(str(exc))


class FlandosyncClient(QMainWindow):
    def __init__(self):
        super().__init__()
        self.external_config = load_external_config()
        self.setWindowTitle(self.external_config.get("app_name", "Flandosync Client"))
        self.setMinimumSize(800, 500)
        self.config_path = os.path.join(app_dir(), "flandosync_client.json")
        self.projects = self.load_config()
        self.current_project = None
        self.pending_manifest = None

        self.init_ui()
        self.apply_theme()

    def load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f).get("projects", [])
            except (OSError, json.JSONDecodeError):
                return []
        return []

    def save_config(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump({"projects": self.projects}, f, ensure_ascii=False, indent=4)

    def apply_theme(self):
        theme = self.external_config.get("theme", "dark").lower()
        if theme == "light":
            self.setStyleSheet("")
            if hasattr(self, "console"):
                self.console.setStyleSheet(
                    "background-color: #ffffff; color: #1f2937; font-family: 'Consolas';"
                )
            return

        self.setStyleSheet(
            """
            QMainWindow, QWidget { background-color: #202124; color: #f3f4f6; }
            QComboBox, QLineEdit, QListWidget, QTextEdit {
                background-color: #111827;
                color: #f3f4f6;
                border: 1px solid #374151;
            }
            QPushButton {
                background-color: #374151;
                color: #f3f4f6;
                border: 1px solid #4b5563;
                padding: 6px;
            }
            QPushButton:disabled { color: #9ca3af; }
            QProgressBar {
                border: 1px solid #4b5563;
                text-align: center;
            }
            QProgressBar::chunk { background-color: #2ecc71; }
            """
        )
        if hasattr(self, "console"):
            self.console.setStyleSheet(
                "background-color: #0b1020; color: #00ff7f; font-family: 'Consolas';"
            )

    def project_display_name(self, project):
        alias = project.get("alias", "").strip()
        name = project.get("name", "Unnamed")
        if alias and alias != name:
            return f"{alias} ({name})"
        return name

    def project_version_label(self, project):
        current_version = project.get("current_version") or project.get("version") or "unknown"
        last_synced_version = project.get("last_synced_version")
        if last_synced_version:
            return f"server {current_version}, synced {last_synced_version}"
        return f"server {current_version}, not synced yet"

    def update_project_status(self, project):
        self.status_label.setText(
            f"Modpack: {self.project_display_name(project)}\nVersion: {self.project_version_label(project)}"
        )

    def refresh_project_list(self):
        self.project_list.clear()
        for index, project in enumerate(self.projects):
            self.project_list.addItem(self.project_display_name(project))
            self.project_list.item(index).setData(Qt.ItemDataRole.UserRole, index)

    def selected_project_index(self):
        item = self.project_list.currentItem()
        if not item:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        left_panel = QVBoxLayout()
        left_panel.addWidget(QLabel("My modpacks:"))
        self.project_list = QListWidget()
        self.project_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.project_list.customContextMenuRequested.connect(self.show_project_context_menu)
        self.project_list.itemClicked.connect(self.select_project)
        self.refresh_project_list()
        left_panel.addWidget(self.project_list)

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("Enter access key")
        left_panel.addWidget(self.key_input)

        add_btn = QPushButton("Add modpack")
        add_btn.clicked.connect(self.add_project)
        left_panel.addWidget(add_btn)

        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self.open_settings)
        left_panel.addWidget(settings_btn)

        right_panel = QVBoxLayout()
        self.status_label = QLabel("Select a modpack")
        self.status_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        right_panel.addWidget(self.status_label)

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet(
            "background-color: #1e1e1e; color: #00ff00; font-family: 'Consolas';"
        )
        right_panel.addWidget(self.console)

        right_panel.addWidget(QLabel("Sync changes:"))
        self.change_list = QListWidget()
        right_panel.addWidget(self.change_list)

        self.progress_bar = QProgressBar()
        right_panel.addWidget(self.progress_bar)

        self.delete_extra_checkbox = QCheckBox("Delete extra files")
        self.delete_extra_checkbox.setToolTip(
            "Delete files in synced folders that are not present in the manifest."
        )
        right_panel.addWidget(self.delete_extra_checkbox)

        export_logs_btn = QPushButton("Export logs")
        export_logs_btn.clicked.connect(self.export_logs)
        right_panel.addWidget(export_logs_btn)

        self.sync_btn = QPushButton("SYNC")
        self.sync_btn.setEnabled(False)
        self.sync_btn.setFixedHeight(40)
        self.sync_btn.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold;")
        self.sync_btn.clicked.connect(self.start_sync)
        right_panel.addWidget(self.sync_btn)

        main_layout.addLayout(left_panel, 1)
        main_layout.addLayout(right_panel, 2)

    def open_settings(self):
        dialog = SettingsDialog(self.external_config, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self.external_config = dialog.get_config()
        save_external_config(self.external_config)
        self.setWindowTitle(self.external_config.get("app_name", "Flandosync Client"))
        self.apply_theme()
        self.console.append("Settings saved.")

    def add_project(self):
        key = self.key_input.text().strip()
        if not key:
            return

        try:
            server_url = normalize_url(self.external_config.get("server_url", "http://localhost:8000"))
            response = requests.get(f"{server_url}/project_by_key", params={"key": key}, timeout=10)
            response.raise_for_status()

            project_info = response.json()
            manifest_url = project_info.get("manifest_url_with_token") or project_info["manifest_url"]
            if manifest_url.startswith("/"):
                manifest_url = urljoin(server_url + "/", manifest_url)
            download_token = project_info.get("download_token", "")
            if download_token and "download_token" not in parse_qs(urlparse(manifest_url).query):
                manifest_url = add_query_param(manifest_url, "download_token", download_token)

            manifest_response = requests.get(manifest_url, timeout=15, headers=auth_headers(download_token))
            manifest_response.raise_for_status()
            manifest = manifest_response.json()
            stored_manifest_url = strip_query_param(manifest_url, "download_token")

            path = QFileDialog.getExistingDirectory(self, "Choose install folder")
            if path:
                new_project = {
                    "name": manifest["name"],
                    "current_version": manifest.get("version", "1.0.0"),
                    "last_synced_version": "",
                    "changelog": manifest.get("changelog", ""),
                    "download_token": download_token,
                    "download_token_expires_at": project_info.get("download_token_expires_at", 0),
                    "key": key,
                    "path": path,
                    "manifest_url": stored_manifest_url,
                }
                self.projects.append(new_project)
                self.save_config()
                self.refresh_project_list()
                self.key_input.clear()
                self.console.append(f"Added modpack: {new_project['name']}")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Could not connect: {exc}")

    def select_project(self, item):
        index = item.data(Qt.ItemDataRole.UserRole)
        self.current_project = self.projects[index] if index is not None else None
        if self.current_project:
            self.update_project_status(self.current_project)
            self.sync_btn.setEnabled(True)
            self.console.append(f"Selected folder: {self.current_project['path']}")

    def show_project_context_menu(self, position):
        item = self.project_list.itemAt(position)
        if not item:
            return

        self.project_list.setCurrentItem(item)
        menu = QMenu(self)
        rename_action = QAction("Rename", self)
        change_folder_action = QAction("Change folder", self)
        remove_action = QAction("Remove", self)
        rename_action.triggered.connect(self.rename_selected_project)
        change_folder_action.triggered.connect(self.change_selected_project_folder)
        remove_action.triggered.connect(self.remove_selected_project)
        menu.addAction(rename_action)
        menu.addAction(change_folder_action)
        menu.addAction(remove_action)
        menu.exec(self.project_list.mapToGlobal(position))

    def rename_selected_project(self):
        index = self.selected_project_index()
        if index is None:
            return

        project = self.projects[index]
        current_alias = project.get("alias") or project["name"]
        alias, accepted = QInputDialog.getText(
            self, "Rename modpack", "Local display name:", text=current_alias
        )
        if not accepted:
            return

        alias = alias.strip()
        if alias and alias != project["name"]:
            project["alias"] = alias
        else:
            project.pop("alias", None)

        self.save_config()
        self.refresh_project_list()
        self.project_list.setCurrentRow(index)
        self.current_project = project
        self.update_project_status(project)

    def change_selected_project_folder(self):
        index = self.selected_project_index()
        if index is None:
            return

        project = self.projects[index]
        current_path = project.get("path", "")
        new_path = QFileDialog.getExistingDirectory(
            self,
            "Choose modpack folder",
            current_path if os.path.isdir(current_path) else os.path.expanduser("~"),
        )
        if not new_path:
            return

        project["path"] = new_path
        self.save_config()
        self.current_project = project
        self.project_list.setCurrentRow(index)
        self.update_project_status(project)
        self.console.append(f"Changed folder: {new_path}")

    def refresh_project_manifest_info(self, project):
        manifest_url = normalize_url(project["manifest_url"])
        download_token = project.get("download_token", "")
        if download_token and "download_token" not in parse_qs(urlparse(manifest_url).query):
            manifest_url = add_query_param(manifest_url, "download_token", download_token)
        response = requests.get(manifest_url, timeout=15, headers=auth_headers(download_token))
        response.raise_for_status()
        manifest = response.json()
        project["current_version"] = manifest.get("version", project.get("current_version", "1.0.0"))
        project["changelog"] = manifest.get("changelog", "")
        project["name"] = manifest.get("name", project.get("name", "Unnamed"))
        with open(manifest_cache_path(manifest_url), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=4)
        self.save_config()
        return manifest

    def refresh_project_access(self, project):
        key = project.get("key", "")
        if not key:
            return

        server_url = normalize_url(self.external_config.get("server_url", "http://localhost:8000"))
        response = requests.get(f"{server_url}/project_by_key", params={"key": key}, timeout=10)
        response.raise_for_status()
        project_info = response.json()
        manifest_url = project_info.get("manifest_url")
        if manifest_url:
            if manifest_url.startswith("/"):
                manifest_url = urljoin(server_url + "/", manifest_url)
            manifest_url = strip_query_param(manifest_url, "download_token")
            project["manifest_url"] = manifest_url
        project["download_token"] = project_info.get("download_token", "")
        project["download_token_expires_at"] = project_info.get("download_token_expires_at", 0)
        self.save_config()

    def warn_if_update_available(self, project):
        try:
            self.refresh_project_access(project)
            manifest = self.refresh_project_manifest_info(project)
        except Exception as exc:
            self.console.append(f"Could not check modpack version: {exc}")
            return

        current_version = manifest.get("version", "1.0.0")
        last_synced_version = project.get("last_synced_version")
        if last_synced_version and current_version != last_synced_version:
            changelog = str(manifest.get("changelog", "")).strip()
            message = (
                f"Update available for {self.project_display_name(project)}.\n\n"
                f"Installed: {last_synced_version}\n"
                f"Server: {current_version}"
            )
            if changelog:
                message += f"\n\nChanges:\n{changelog}"
            QMessageBox.information(self, "Modpack update", message)

        self.update_project_status(project)

    def remove_selected_project(self):
        index = self.selected_project_index()
        if index is None:
            return

        project = self.projects[index]
        dialog = QDialog(self)
        dialog.setWindowTitle("Remove modpack")
        layout = QVBoxLayout(dialog)
        layout.addWidget(
            QLabel(
                f"Remove '{self.project_display_name(project)}' from the local list?\n"
                "Files are kept unless the checkbox below is enabled."
            )
        )
        delete_files_checkbox = QCheckBox("Also permanently delete synced files")
        layout.addWidget(delete_files_checkbox)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        if delete_files_checkbox.isChecked():
            try:
                deleted = self.delete_project_files(project)
                self.console.append(f"Removed synced files: {deleted}")
            except Exception as exc:
                QMessageBox.critical(self, "Error", f"Could not delete synced files: {exc}")
                return

        removed = self.projects.pop(index)
        self.save_config()
        self.refresh_project_list()
        self.current_project = None
        self.sync_btn.setEnabled(False)
        self.status_label.setText("Select a modpack")
        self.console.append(f"Removed modpack from list: {self.project_display_name(removed)}")

    def delete_project_files(self, project):
        manifest_url = normalize_url(project["manifest_url"])
        response = requests.get(manifest_url, timeout=15)
        response.raise_for_status()
        manifest = response.json()

        project_root = os.path.abspath(project["path"])
        deleted = 0
        for file_info in manifest.get("files", []):
            rel_path = file_info["path"]
            local_path = os.path.abspath(os.path.join(project_root, rel_path))
            if os.path.commonpath([project_root, local_path]) != project_root:
                raise ValueError(f"Unsafe path in manifest: {rel_path}")
            if os.path.isfile(local_path):
                os.remove(local_path)
                deleted += 1
                self.change_list.addItem(f"[Removed] {rel_path}")

        return deleted

    def export_logs(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export logs", "flandosync-log.txt", "Text files (*.txt)")
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            f.write("Flandosync log\n")
            f.write("=" * 40 + "\n\n")
            f.write(self.console.toPlainText())
            f.write("\n\nSync changes\n")
            f.write("=" * 40 + "\n")
            for index in range(self.change_list.count()):
                f.write(self.change_list.item(index).text() + "\n")

        self.console.append(f"Logs exported: {path}")

    def start_sync(self):
        if not self.current_project:
            return

        self.sync_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.change_list.clear()
        self.pending_manifest = None
        self.warn_if_update_available(self.current_project)

        self.worker = SyncWorker(
            self.current_project["path"],
            self.current_project["manifest_url"],
            self.delete_extra_checkbox.isChecked(),
            self.external_config,
            self.current_project.get("download_token", ""),
        )
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.log.connect(lambda msg: self.console.append(msg))
        self.worker.result.connect(lambda kind, path: self.change_list.addItem(f"[{kind}] {path}"))
        self.worker.manifest_loaded.connect(self.on_manifest_loaded)
        self.worker.finished.connect(self.on_sync_finished)
        self.worker.start()

    def on_manifest_loaded(self, manifest):
        self.pending_manifest = manifest

    def on_sync_finished(self, success):
        self.sync_btn.setEnabled(True)
        if success:
            if self.current_project and self.pending_manifest:
                self.current_project["current_version"] = self.pending_manifest.get(
                    "version", self.current_project.get("current_version", "1.0.0")
                )
                self.current_project["last_synced_version"] = self.current_project["current_version"]
                self.current_project["changelog"] = self.pending_manifest.get("changelog", "")
                self.current_project["name"] = self.pending_manifest.get(
                    "name", self.current_project.get("name", "Unnamed")
                )
                self.save_config()
                self.refresh_project_list()
                self.update_project_status(self.current_project)
            QMessageBox.information(self, "Done", "Sync completed.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FlandosyncClient()
    window.show()
    sys.exit(app.exec())
