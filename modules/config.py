# modules/config.py
import os
import json
import logging
from typing import Any, Dict
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit,
    QRadioButton, QPushButton, QMessageBox, QButtonGroup
)
from .constants import ( # 定数をインポート
    CONFIG_FILE_NAME, ConfigKeys, DEFAULT_CONFIG,
    PREVIEW_MODE_SEAMLESS, PREVIEW_MODE_WHEEL,
    OUTPUT_FORMAT_SEPARATE, OUTPUT_FORMAT_INLINE
)

logger = logging.getLogger(__name__)

class ConfigManager:
    """
    アプリケーションの設定ファイルの読み込みと保存を管理するクラス。
    設定は JSON 形式で保存されます。
    """
    CONFIG_FILE = CONFIG_FILE_NAME

    @staticmethod
    def load_config() -> Dict[str, Any]:
        """
        設定ファイルから設定を読み込みます。
        ファイルが存在しない場合や読み込みに失敗した場合は、
        デフォルト値を返します。

        Returns:
            設定値を含む辞書。
        """
        config_data = DEFAULT_CONFIG.copy() # まずデフォルト値で初期化
        if os.path.exists(ConfigManager.CONFIG_FILE):
            try:
                with open(ConfigManager.CONFIG_FILE, "r", encoding='utf-8') as file:
                    loaded_data = json.load(file)
                    # 読み込んだデータでデフォルト値を上書き
                    config_data.update(loaded_data)
                    logger.info(f"設定ファイルを読み込みました: {ConfigManager.CONFIG_FILE}")
            except (FileNotFoundError, IOError) as e:
                logger.error(f"設定ファイルの読み込み中にエラーが発生しました: {e}", exc_info=True)
            except json.JSONDecodeError as e:
                logger.error(f"設定ファイルのJSONデコードに失敗しました: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"設定ファイルの読み込み中に予期せぬエラーが発生しました: {e}", exc_info=True)
        else:
            logger.info(f"設定ファイルが見つかりません。デフォルト設定を使用します: {ConfigManager.CONFIG_FILE}")
            # ファイルが存在しない場合はデフォルト値を保存しておく
            ConfigManager.save_config(config_data)

        # 念のため、デフォルトに含まれるキーが欠けていないか確認
        for key, value in DEFAULT_CONFIG.items():
            if key not in config_data:
                logger.warning(f"設定ファイルにキー '{key}' がありません。デフォルト値 '{value}' を使用します。")
                config_data[key] = value

        return config_data

    @staticmethod
    def save_config(config: Dict[str, Any]) -> None:
        """
        現在の設定をJSONファイルに保存します。

        Args:
            config: 保存する設定値を含む辞書。
        """
        try:
            with open(ConfigManager.CONFIG_FILE, "w", encoding='utf-8') as file:
                json.dump(config, file, indent=4, ensure_ascii=False)
            logger.info(f"設定をファイルに保存しました: {ConfigManager.CONFIG_FILE}")
        except IOError as e:
            logger.error(f"設定ファイルの書き込み中にエラーが発生しました: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"設定ファイルの保存中に予期せぬエラーが発生しました: {e}", exc_info=True)

class ConfigDialog(QDialog):
    """
    アプリケーション設定を変更するためのダイアログウィンドウ。
    キャッシュサイズ、プレビューモード、出力フォーマットを設定できます。
    """
    def __init__(self, current_cache_size: int,
                 current_preview_mode: str = PREVIEW_MODE_SEAMLESS,
                 current_output_format: str = OUTPUT_FORMAT_SEPARATE,
                 parent: Any = None):
        """
        ConfigDialogを初期化します。

        Args:
            current_cache_size: 現在のキャッシュサイズ。
            current_preview_mode: 現在のプレビューモード。
            current_output_format: 現在の出力フォーマット。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self.setWindowTitle("Config Settings")
        # 親ウィンドウへの参照を保持（MainWindowのupdate_configを呼び出すため）
        self.parent_window = parent

        # 設定値を保持するメンバ変数
        self._current_cache_size = current_cache_size
        self._current_preview_mode = current_preview_mode
        self._current_output_format = current_output_format

        # UI要素のプレースホルダー
        self.cache_size_input: QLineEdit = None
        self.seamless_radio: QRadioButton = None
        self.wheel_radio: QRadioButton = None
        self.separate_lines_radio: QRadioButton = None
        self.inline_format_radio: QRadioButton = None

        self.initUI()

    def initUI(self) -> None:
        """ダイアログのUIを初期化し、レイアウトを設定します。"""
        layout = QVBoxLayout(self)

        # 各設定グループを作成
        cache_group = self._create_cache_group()
        preview_group = self._create_preview_group()
        output_format_group = self._create_output_format_group()

        # レイアウトに追加
        layout.addWidget(cache_group)
        layout.addWidget(preview_group)
        layout.addWidget(output_format_group)

        # Apply Button
        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(self.apply_changes)
        layout.addWidget(apply_button)

    def _create_cache_group(self) -> QGroupBox:
        """キャッシュ設定グループを作成します。"""
        cache_group = QGroupBox("Cache Settings")
        cache_layout = QVBoxLayout()
        cache_label = QLabel("Cache Size (number of thumbnails):")
        self.cache_size_input = QLineEdit(str(self._current_cache_size))
        # 数値のみ入力できるようにバリデータを設定することも可能
        # from PyQt6.QtGui import QIntValidator
        # self.cache_size_input.setValidator(QIntValidator(1, 99999)) # 例: 1から99999まで
        cache_layout.addWidget(cache_label)
        cache_layout.addWidget(self.cache_size_input)
        cache_group.setLayout(cache_layout)
        return cache_group

    def _create_preview_group(self) -> QGroupBox:
        """プレビューモード設定グループを作成します。"""
        display_group = QGroupBox("Preview Mode (Image Dialog)")
        display_layout = QVBoxLayout()
        self.seamless_radio = QRadioButton("Seamless (Fit to window)")
        self.wheel_radio = QRadioButton("Wheel (Zoom with Ctrl+Wheel, Pan with Drag)")

        # QButtonGroupで排他制御
        preview_group_btns = QButtonGroup(self)
        preview_group_btns.addButton(self.seamless_radio)
        preview_group_btns.addButton(self.wheel_radio)

        if self._current_preview_mode == PREVIEW_MODE_SEAMLESS:
            self.seamless_radio.setChecked(True)
        else:
            self.wheel_radio.setChecked(True)

        display_layout.addWidget(self.seamless_radio)
        display_layout.addWidget(self.wheel_radio)
        display_group.setLayout(display_layout)
        return display_group

    def _create_output_format_group(self) -> QGroupBox:
        """出力フォーマット設定グループを作成します。"""
        output_format_group = QGroupBox("Output Format (WC Creator)")
        output_format_layout = QVBoxLayout()
        self.separate_lines_radio = QRadioButton("Separate lines (# comment)")
        self.inline_format_radio = QRadioButton("Inline format ([comment:100]prompt)")

        # QButtonGroupで排他制御
        output_group_btns = QButtonGroup(self)
        output_group_btns.addButton(self.separate_lines_radio)
        output_group_btns.addButton(self.inline_format_radio)

        if self._current_output_format == OUTPUT_FORMAT_SEPARATE:
            self.separate_lines_radio.setChecked(True)
        else:
            self.inline_format_radio.setChecked(True)

        output_format_layout.addWidget(self.separate_lines_radio)
        output_format_layout.addWidget(self.inline_format_radio)
        output_format_group.setLayout(output_format_layout)
        return output_format_group

    def apply_changes(self) -> None:
        """
        「Apply」ボタンがクリックされたときの処理。
        入力値を検証し、親ウィンドウに変更を通知してダイアログを閉じます。
        """
        try:
            # キャッシュサイズの検証
            new_cache_size_str = self.cache_size_input.text()
            new_cache_size = int(new_cache_size_str)
            if new_cache_size <= 0:
                 raise ValueError("Cache size must be a positive integer.")

            # プレビューモードの取得
            preview_mode = PREVIEW_MODE_SEAMLESS if self.seamless_radio.isChecked() else PREVIEW_MODE_WHEEL

            # 出力フォーマットの取得
            output_format = OUTPUT_FORMAT_SEPARATE if self.separate_lines_radio.isChecked() else OUTPUT_FORMAT_INLINE

            # 親ウィンドウの更新メソッドを呼び出し
            if self.parent_window and hasattr(self.parent_window, 'update_config'):
                self.parent_window.update_config(new_cache_size, preview_mode, output_format)
                logger.info(f"設定が更新されました: Cache={new_cache_size}, Preview='{preview_mode}', Output='{output_format}'")
                self.accept() # QDialogを閉じる（OK相当）
            else:
                 logger.warning("親ウィンドウが見つからないか、update_configメソッドがありません。")
                 QMessageBox.warning(self, "Error", "Could not apply settings to the main window.")

        except ValueError as e:
            logger.warning(f"設定の適用中に無効な入力がありました: {e}", exc_info=False)
            QMessageBox.warning(self, "Invalid Input", f"Invalid input for Cache Size: {e}\nPlease enter a positive number.")
        except Exception as e:
             logger.error(f"設定の適用中に予期せぬエラーが発生しました: {e}", exc_info=True)
             QMessageBox.critical(self, "Error", f"An unexpected error occurred: {e}")