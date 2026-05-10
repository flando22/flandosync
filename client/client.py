import hashlib
import json
import os
import sys
from urllib.parse import urljoin

import requests
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
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


class SyncWorker(QThread):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    result = pyqtSignal(str, str)
    finished = pyqtSignal(bool)

    def __init__(self, project_path, manifest_url, delete_extra=False):
        super().__init__()
        self.project_path = project_path
        self.manifest_url = manifest_url
        self.delete_extra = delete_extra

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

    def download_file(self, download_url, local_path, expected_hash):
        response = requests.get(download_url, stream=True, timeout=60)
        response.raise_for_status()

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

    def run(self):
        try:
            self.log.emit("Loading manifest...")
            manifest_url = normalize_url(self.manifest_url)
            response = requests.get(manifest_url, timeout=15)
            response.raise_for_status()
            manifest = response.json()

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

            for index, file_info in enumerate(files):
                rel_path = file_info["path"]
                remote_hash = file_info["sha256"]
                download_url = urljoin(manifest_url, file_info["url"])
                local_path = self.safe_local_path(rel_path)
                expected_paths.add(os.path.normcase(local_path))
                sync_roots.add(rel_path.replace("\\", "/").split("/", 1)[0])

                os.makedirs(os.path.dirname(local_path), exist_ok=True)

                needs_download = True
                if os.path.exists(local_path):
                    local_hash = self.get_file_hash(local_path)
                    if local_hash == remote_hash:
                        needs_download = False
                        self.log.emit(f"Skipped: {rel_path} is already up to date")
                        self.result.emit("Skipped", rel_path)

                if needs_download:
                    self.log.emit(f"Downloading: {rel_path}...")
                    self.download_file(download_url, local_path, remote_hash)
                    self.result.emit("Downloaded", rel_path)

                self.progress.emit(int(((index + 1) / total_files) * 100))

            if self.delete_extra:
                self.log.emit("Deleting files that are not in the manifest...")
                self.delete_files_not_in_manifest(expected_paths, sync_roots)

            self.log.emit("Sync completed successfully.")
            self.finished.emit(True)
        except Exception as exc:
            self.log.emit(f"ERROR: {exc}")
            self.finished.emit(False)


class FlandosyncClient(QMainWindow):
    def __init__(self):
        super().__init__()
        self.external_config = load_external_config()
        self.setWindowTitle(self.external_config.get("app_name", "Flandosync Client"))
        self.setMinimumSize(800, 500)
        self.config_path = os.path.join(app_dir(), "flandosync_client.json")
        self.projects = self.load_config()
        self.current_project = None

        self.init_ui()

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

    def project_display_name(self, project):
        alias = project.get("alias", "").strip()
        name = project.get("name", "Unnamed")
        if alias and alias != name:
            return f"{alias} ({name})"
        return name

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

    def add_project(self):
        key = self.key_input.text().strip()
        if not key:
            return

        try:
            server_url = normalize_url(self.external_config.get("server_url", "http://localhost:8000"))
            response = requests.get(f"{server_url}/project_by_key", params={"key": key}, timeout=10)
            response.raise_for_status()

            manifest_url = response.json()["manifest_url"]
            if manifest_url.startswith("/"):
                manifest_url = urljoin(server_url + "/", manifest_url)

            manifest_response = requests.get(manifest_url, timeout=15)
            manifest_response.raise_for_status()
            manifest = manifest_response.json()

            path = QFileDialog.getExistingDirectory(self, "Choose install folder")
            if path:
                new_project = {
                    "name": manifest["name"],
                    "key": key,
                    "path": path,
                    "manifest_url": manifest_url,
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
            self.status_label.setText(f"Modpack: {self.project_display_name(self.current_project)}")
            self.sync_btn.setEnabled(True)
            self.console.append(f"Selected folder: {self.current_project['path']}")

    def show_project_context_menu(self, position):
        item = self.project_list.itemAt(position)
        if not item:
            return

        self.project_list.setCurrentItem(item)
        menu = QMenu(self)
        rename_action = QAction("Rename", self)
        remove_action = QAction("Remove", self)
        rename_action.triggered.connect(self.rename_selected_project)
        remove_action.triggered.connect(self.remove_selected_project)
        menu.addAction(rename_action)
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
        self.status_label.setText(f"Modpack: {self.project_display_name(project)}")

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

        self.worker = SyncWorker(
            self.current_project["path"],
            self.current_project["manifest_url"],
            self.delete_extra_checkbox.isChecked(),
        )
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.log.connect(lambda msg: self.console.append(msg))
        self.worker.result.connect(lambda kind, path: self.change_list.addItem(f"[{kind}] {path}"))
        self.worker.finished.connect(self.on_sync_finished)
        self.worker.start()

    def on_sync_finished(self, success):
        self.sync_btn.setEnabled(True)
        if success:
            QMessageBox.information(self, "Done", "Sync completed.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FlandosyncClient()
    window.show()
    sys.exit(app.exec())
