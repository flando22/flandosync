import json
import os
import shlex
import subprocess
import sys

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


DEFAULT_CONFIG = {
    "app_name": "Flandosync Admin",
    "ssh_host": "example.com",
    "ssh_port": 22,
    "ssh_user": "flandosync-admin",
    "ssh_key_path": "",
    "remote_project_dir": "/opt/flandosync",
    "python_command": "python3",
    "service_name": "",
}


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def settings_path():
    return os.path.join(app_dir(), "admin_settings.json")


def load_config():
    path = settings_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except (OSError, json.JSONDecodeError):
            return DEFAULT_CONFIG

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=4)
    except OSError:
        pass
    return DEFAULT_CONFIG


def save_config(config):
    with open(settings_path(), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)


def quote_remote(value):
    return shlex.quote(str(value))


class SshWorker(QThread):
    output = pyqtSignal(str)
    finished = pyqtSignal(bool)

    def __init__(self, config, remote_command):
        super().__init__()
        self.config = dict(config)
        self.remote_command = remote_command

    def ssh_args(self):
        target = f"{self.config['ssh_user']}@{self.config['ssh_host']}"
        args = [
            "ssh",
            "-p",
            str(self.config.get("ssh_port", 22)),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
        ]
        key_path = str(self.config.get("ssh_key_path", "")).strip()
        if key_path:
            args.extend(["-i", key_path])
        args.extend([target, self.remote_command])
        return args

    def run(self):
        try:
            process = subprocess.run(
                self.ssh_args(),
                text=True,
                capture_output=True,
                timeout=120,
                check=False,
            )
            if process.stdout:
                self.output.emit(process.stdout.rstrip())
            if process.stderr:
                self.output.emit(process.stderr.rstrip())
            self.finished.emit(process.returncode == 0)
        except Exception as exc:
            self.output.emit(f"ERROR: {exc}")
            self.finished.emit(False)


class FlandosyncAdmin(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.worker = None
        self.current_action = None
        self.command_output = []
        self.setWindowTitle(self.config.get("app_name", "Flandosync Admin"))
        self.setMinimumSize(820, 560)
        self.init_ui()
        self.load_fields()

    def init_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        form = QFormLayout()
        self.host_input = QLineEdit()
        self.port_input = QLineEdit()
        self.user_input = QLineEdit()
        self.key_input = QLineEdit()
        self.remote_dir_input = QLineEdit()
        self.python_input = QLineEdit()
        self.service_input = QLineEdit()

        key_row = QHBoxLayout()
        key_row.addWidget(self.key_input)
        browse_key_btn = QPushButton("Browse")
        browse_key_btn.clicked.connect(self.browse_key)
        key_row.addWidget(browse_key_btn)

        form.addRow("SSH host:", self.host_input)
        form.addRow("SSH port:", self.port_input)
        form.addRow("SSH user:", self.user_input)
        form.addRow("SSH key:", key_row)
        form.addRow("Remote project dir:", self.remote_dir_input)
        form.addRow("Python command:", self.python_input)
        form.addRow("Systemd service:", self.service_input)
        layout.addLayout(form)

        settings_row = QHBoxLayout()
        save_btn = QPushButton("Save settings")
        save_btn.clicked.connect(self.save_fields)
        test_btn = QPushButton("Test SSH")
        test_btn.clicked.connect(self.test_ssh)
        list_btn = QPushButton("List modpacks")
        list_btn.clicked.connect(self.list_modpacks)
        settings_row.addWidget(save_btn)
        settings_row.addWidget(test_btn)
        settings_row.addWidget(list_btn)
        layout.addLayout(settings_row)

        layout.addWidget(QLabel("Modpacks:"))
        self.modpack_list = QListWidget()
        self.modpack_list.itemSelectionChanged.connect(self.fill_selected_modpack)
        layout.addWidget(self.modpack_list)

        action_form = QFormLayout()
        self.modpack_input = QLineEdit()
        self.version_input = QLineEdit()
        self.changelog_input = QLineEdit()
        action_form.addRow("Modpack:", self.modpack_input)
        action_form.addRow("Version:", self.version_input)
        action_form.addRow("Changelog:", self.changelog_input)
        layout.addLayout(action_form)

        action_row = QHBoxLayout()
        generate_btn = QPushButton("Generate manifest")
        generate_btn.clicked.connect(self.generate_manifest)
        restart_btn = QPushButton("Restart service")
        restart_btn.clicked.connect(self.restart_service)
        self.confirm_restart = QCheckBox("Confirm restart")
        action_row.addWidget(generate_btn)
        action_row.addWidget(restart_btn)
        action_row.addWidget(self.confirm_restart)
        layout.addLayout(action_row)

        layout.addWidget(QLabel("Output:"))
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output)

    def load_fields(self):
        self.host_input.setText(str(self.config.get("ssh_host", "")))
        self.port_input.setText(str(self.config.get("ssh_port", 22)))
        self.user_input.setText(str(self.config.get("ssh_user", "")))
        self.key_input.setText(str(self.config.get("ssh_key_path", "")))
        self.remote_dir_input.setText(str(self.config.get("remote_project_dir", "")))
        self.python_input.setText(str(self.config.get("python_command", "python3")))
        self.service_input.setText(str(self.config.get("service_name", "")))

    def current_config(self):
        config = {**DEFAULT_CONFIG, **self.config}
        config["ssh_host"] = self.host_input.text().strip()
        config["ssh_port"] = self.port_input.text().strip() or "22"
        config["ssh_user"] = self.user_input.text().strip()
        config["ssh_key_path"] = self.key_input.text().strip()
        config["remote_project_dir"] = self.remote_dir_input.text().strip()
        config["python_command"] = self.python_input.text().strip() or "python3"
        config["service_name"] = self.service_input.text().strip()
        return config

    def save_fields(self):
        self.config = self.current_config()
        save_config(self.config)
        self.output.append("Settings saved.")

    def browse_key(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose SSH key")
        if path:
            self.key_input.setText(path)

    def remote_project_dir(self):
        return quote_remote(self.current_config()["remote_project_dir"])

    def run_remote(self, remote_command, action=None):
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "Busy", "Another admin command is still running.")
            return

        self.config = self.current_config()
        save_config(self.config)
        self.current_action = action
        self.command_output = []
        self.output.append(f"$ {remote_command}")
        self.worker = SshWorker(self.config, remote_command)
        self.worker.output.connect(self.on_command_output)
        self.worker.finished.connect(self.on_command_finished)
        self.worker.start()

    def on_command_output(self, text):
        self.command_output.append(text)
        self.output.append(text)

    def on_command_finished(self, success):
        if success and self.current_action == "list_modpacks":
            self.modpack_list.clear()
            names = []
            for block in self.command_output:
                for line in block.splitlines():
                    name = line.strip()
                    if name:
                        names.append(name)
            self.modpack_list.addItems(sorted(set(names)))
        self.output.append("OK" if success else "FAILED")
        self.current_action = None

    def test_ssh(self):
        self.run_remote("printf 'flandosync-admin-ok\\n'")

    def list_modpacks(self):
        remote_dir = self.remote_project_dir()
        command = (
            f"cd {remote_dir} && "
            "if [ -d modpacks ]; then find modpacks -mindepth 1 -maxdepth 1 -type d -printf '%f\\n' | sort; fi"
        )
        self.run_remote(command, action="list_modpacks")

    def fill_selected_modpack(self):
        item = self.modpack_list.currentItem()
        if item:
            self.modpack_input.setText(item.text())

    def generate_manifest(self):
        modpack = self.modpack_input.text().strip()
        if not modpack:
            QMessageBox.warning(self, "Missing modpack", "Enter or select a modpack name.")
            return

        remote_dir = self.remote_project_dir()
        python_command = quote_remote(self.current_config()["python_command"])
        command_parts = [
            f"cd {remote_dir}",
            f"{python_command} server.py -generate {quote_remote(modpack)}",
        ]
        version = self.version_input.text().strip()
        changelog = self.changelog_input.text().strip()
        if version:
            command_parts[1] += f" -version {quote_remote(version)}"
        if changelog:
            command_parts[1] += f" -changelog {quote_remote(changelog)}"
        self.run_remote(" && ".join(command_parts))

    def restart_service(self):
        service = self.current_config().get("service_name", "").strip()
        if not service:
            QMessageBox.warning(self, "Missing service", "Set a systemd service name first.")
            return
        if not self.confirm_restart.isChecked():
            QMessageBox.warning(self, "Confirm restart", "Enable the confirmation checkbox first.")
            return

        command = f"sudo systemctl restart {quote_remote(service)}"
        self.run_remote(command)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FlandosyncAdmin()
    window.show()
    sys.exit(app.exec())
