# g:\vscodeGit\modules\config.py
import os
import json
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QGroupBox, QLabel, QLineEdit, QRadioButton, QPushButton, QMessageBox

class ConfigManager:
    CONFIG_FILE = "last_value.json"

    @staticmethod
    def load_config():
        if os.path.exists(ConfigManager.CONFIG_FILE):
            try:
                with open(ConfigManager.CONFIG_FILE, "r") as file:
                    data = json.load(file)
            except Exception as e:
                print(f"Error loading config: {e}")
                data = {}
        else:
            data = {}
        defaults = {
            "folder": "",
            "thumbnail_columns": 5,
            "cache_size": 1000,
            "sort_order": "filename_asc",
            "preview_mode": "seamless",
            "output_format": "separate_lines"
        }
        for key, value in defaults.items():
            if key not in data:
                data[key] = value
        return data

    @staticmethod
    def save_config(config):
        try:
            with open(ConfigManager.CONFIG_FILE, "w") as file:
                json.dump(config, file, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")

class ConfigDialog(QDialog):
    def __init__(self, current_cache_size, current_preview_mode="seamless", current_output_format="separate_lines", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Config Settings")
        self.current_cache_size = current_cache_size
        self.current_preview_mode = current_preview_mode
        self.current_output_format = current_output_format
        self.parent_window = parent # MainWindow の参照
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)

        # Cache Settings
        cache_group = QGroupBox("Cache Settings")
        cache_layout = QVBoxLayout()
        cache_label = QLabel("Cache Size:")
        self.cache_size_input = QLineEdit(str(self.current_cache_size))
        cache_layout.addWidget(cache_label)
        cache_layout.addWidget(self.cache_size_input)
        cache_group.setLayout(cache_layout)
        layout.addWidget(cache_group)

        # Preview Mode
        display_group = QGroupBox("Preview Mode")
        display_layout = QVBoxLayout()
        self.seamless_radio = QRadioButton("シームレス")
        self.wheel_radio = QRadioButton("ホイール")
        if self.current_preview_mode == "seamless":
            self.seamless_radio.setChecked(True)
        else:
            self.wheel_radio.setChecked(True)
        display_layout.addWidget(self.seamless_radio)
        display_layout.addWidget(self.wheel_radio)
        display_group.setLayout(display_layout)
        layout.addWidget(display_group)

        # Output Format
        output_format_group = QGroupBox("出力フォーマット")
        output_format_layout = QVBoxLayout()
        self.separate_lines_radio = QRadioButton("行頭に '#' を付けて別行に出力")
        self.inline_format_radio = QRadioButton("[:100]で先頭に出力")
        if self.current_output_format == "separate_lines":
            self.separate_lines_radio.setChecked(True)
        else:
            self.inline_format_radio.setChecked(True)
        output_format_layout.addWidget(self.separate_lines_radio)
        output_format_layout.addWidget(self.inline_format_radio)
        output_format_group.setLayout(output_format_layout)
        layout.addWidget(output_format_group)

        # Apply Button
        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(self.apply_changes)
        layout.addWidget(apply_button)

    def apply_changes(self):
        try:
            new_cache_size = int(self.cache_size_input.text())
            preview_mode = "seamless" if self.seamless_radio.isChecked() else "wheel"
            output_format = "separate_lines" if self.separate_lines_radio.isChecked() else "inline_format"

            # MainWindow の ActionHandler の update_config を呼び出す
            if self.parent_window and hasattr(self.parent_window, 'action_handler') and self.parent_window.action_handler:
                self.parent_window.action_handler.update_config(new_cache_size, preview_mode, output_format)
            else:
                 QMessageBox.warning(self, "Error", "Could not apply changes. Parent window or ActionHandler not found.")

            self.close()
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter a valid number for Cache Size.")
        except Exception as e:
             QMessageBox.critical(self, "Error", f"An error occurred while applying changes: {e}")

