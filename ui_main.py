# \ui_main.py
import os
import sys
import json
import logging # logging をインポート
# import shutil # FileManager に移動
# import re # FileManager に移動
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QStatusBar, QTreeView, QSplitter, QGridLayout, QLineEdit, QLabel, QScrollArea,
    QButtonGroup, QRadioButton, QMessageBox, QApplication
)
from PyQt6.QtCore import Qt, QProcess, QUrl
from PyQt6.QtGui import QFileSystemModel, QScreen
# ActionHandler が使うのでインポートは残す
from modules.thumbnail_cache import ThumbnailCache
from modules.image_loader import ImageLoader
from modules.config import ConfigDialog, ConfigManager
from modules.metadata import extract_metadata
from modules.thumbnail_widget import ImageThumbnail
from modules.image_dialog import MetadataDialog, ImageDialog
from modules.drop_window import DropWindow
from modules.file_manager import FileManager
from modules.image_data_manager import ImageDataManager
# --- ここまで ---
from modules.thumbnail_view_controller import ThumbnailViewController # ActionHandler が使う
from modules.app_state import AppState # AppState をインポート
from modules.ui_manager import UIManager # ActionHandler が使う
from modules.action_handler import ActionHandler # ActionHandler をインポート
from modules.wc_creator import WCCreatorDialog # ActionHandler が使う

logger = logging.getLogger(__name__) # ロガーを取得

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Move/Copy Application")
        self.setGeometry(100, 100, 1500, 800)

        # --- 状態管理クラス ---
        config_temp = ConfigManager.load_config()
        initial_sort = config_temp.get("sort_order", "filename_asc")
        initial_columns = config_temp.get("thumbnail_columns", 5)
        self.app_state = AppState(initial_sort=initial_sort, initial_columns=initial_columns)

        # --- 主要コンポーネントの生成と初期化 ---
        # ActionHandler (アプリケーションの中心)
        self.action_handler = ActionHandler(self, self.app_state)
        # ActionHandler に UI マネージャーとビューコントローラーの初期化を依頼
        self.action_handler.initialize_components()

        # --- UI関連のインスタンス変数 (ActionHandlerが管理) ---
        # self.ui_manager = None
        # self.thumbnail_view_controller = None

        # --- シグナル接続 (ActionHandler 内で実行) ---
        # self._connect_app_state_signals()
        # self._connect_data_manager_signals()

        # --- 初期画像読み込み ---
        if self.action_handler:
            self.action_handler.load_images()
        else:
            # このエラーは ActionHandler の初期化失敗時に発生するはず
            logger.critical("ActionHandler could not be initialized.")


    # initUI メソッドは不要になった
    # def initUI(self):
    #     pass

    # _connect_app_state_signals メソッドは不要になった
    # def _connect_app_state_signals(self):
    #     pass

    # --- Signal Handlers / Slots ---
    # (すべて移動済み)

    # --- Core Logic Methods ---

    def closeEvent(self, event):
        """ウィンドウ終了時の処理 (ActionHandlerに委譲)"""
        if self.action_handler:
            self.action_handler.handle_close()
        super().closeEvent(event)

# --- main.py から呼び出される部分 ---
# ... (変更なし) ...
