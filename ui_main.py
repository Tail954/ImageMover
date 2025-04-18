# ui_main.py
import os
import sys
import json
import shutil
import logging
import re
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QStatusBar, QTreeView, QSplitter, QGridLayout, QLineEdit, QLabel, QScrollArea,
    QButtonGroup, QRadioButton, QMessageBox, QApplication # QApplication をインポート
)
from PyQt6.QtCore import Qt, QProcess, QCoreApplication, QMetaObject, Q_ARG, QDir
from PyQt6.QtGui import QFileSystemModel, QIcon, QCloseEvent

# 自作モジュールと定数のインポート
from modules.thumbnail_cache import ThumbnailCache
from modules.image_loader import ImageLoader
from modules.config import ConfigDialog, ConfigManager
from modules.metadata import extract_metadata # メタデータ抽出関数
from modules.thumbnail_widget import ImageThumbnail # サムネイルウィジェット
from modules.image_dialog import MetadataDialog, ImageDialog # ダイアログ
from modules.wc_creator import WCCreatorDialog # WC Creator Dialog
from modules.constants import ( # 定数
    ConfigKeys, DEFAULT_CONFIG,
    MIN_THUMBNAIL_COLUMNS, MAX_THUMBNAIL_COLUMNS, DEFAULT_THUMBNAIL_SIZE,
    SORT_FILENAME_ASC, SORT_FILENAME_DESC, SORT_DATE_ASC, SORT_DATE_DESC,
    PREVIEW_MODE_SEAMLESS, PREVIEW_MODE_WHEEL,
    OUTPUT_FORMAT_SEPARATE, OUTPUT_FORMAT_INLINE,
    VALID_IMAGE_EXTENSIONS # 必要であれば使用
)

# Send2Trash のインポート
try:
    from send2trash import send2trash
except ImportError:
    logger.warning("send2trash がインストールされていません。空フォルダ削除機能は無効になります。")
    send2trash = None # send2trash がない場合は None に

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    """
    アプリケーションのメインウィンドウクラス。
    フォルダ内の画像を管理し、移動、コピー、メタデータ表示などを行います。
    """
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Image Management Tool")
        self.setGeometry(100, 100, 1500, 800) # 初期サイズ
        self._setup_window_icon() # アイコン設定

        # --- 状態変数 ---
        self._current_folder: Optional[str] = None
        self._images: List[str] = []                # 現在のフォルダの全画像パスリスト (ソート済み)
        self._filtered_images: Optional[List[str]] = None # フィルタ適用後の画像パスリスト (ソート済み)
        self._copy_mode: bool = False          # コピー（複数選択・順序付け）モードか否か
        # コピーモード時の選択された ImageThumbnail インスタンスのリスト (選択順)
        self._selection_order: List[ImageThumbnail] = []

        # --- 設定値 (Config) ---
        self._config_data: Dict[str, Any] = {}
        self._thumbnail_columns: int = DEFAULT_CONFIG[ConfigKeys.THUMBNAIL_COLUMNS]
        self._cache_size: int = DEFAULT_CONFIG[ConfigKeys.CACHE_SIZE]
        self._current_sort: str = DEFAULT_CONFIG[ConfigKeys.SORT_ORDER]
        self._preview_mode: str = DEFAULT_CONFIG[ConfigKeys.PREVIEW_MODE]
        self._output_format: str = DEFAULT_CONFIG[ConfigKeys.OUTPUT_FORMAT]
        self._load_config() # 設定値をロード

        # --- コアコンポーネント ---
        self._thumbnail_cache = ThumbnailCache(max_size=self._cache_size)
        self._image_loader: Optional[ImageLoader] = None
        self._metadata_dialog: Optional[MetadataDialog] = None

        # --- UI要素プレースホルダー ---
        self.central_widget: QWidget = None
        self.config_button: QPushButton = None
        self.toggle_tree_button: QPushButton = None
        self.splitter: QSplitter = None
        self.folder_model: QFileSystemModel = None
        self.tree_view: QTreeView = None
        self.image_area_widget: QWidget = None
        self.decrement_col_button: QPushButton = None
        self.columns_display: QLineEdit = None
        self.increment_col_button: QPushButton = None
        self.filter_box: QLineEdit = None
        self.filter_button: QPushButton = None
        self.and_radio: QRadioButton = None
        self.or_radio: QRadioButton = None
        self.filter_mode_group: QButtonGroup = None
        self.filename_asc_radio: QPushButton = None
        self.filename_desc_radio: QPushButton = None
        self.date_asc_radio: QPushButton = None
        self.date_desc_radio: QPushButton = None
        self.sort_group: QButtonGroup = None
        self.select_all_button: QPushButton = None
        self.unselect_button: QPushButton = None
        self.copy_mode_button: QPushButton = None
        self.scroll_area: QScrollArea = None
        self.grid_widget: QWidget = None
        self.grid_layout: QGridLayout = None
        self.wc_creator_button: QPushButton = None
        self.move_button: QPushButton = None
        self.copy_button: QPushButton = None
        self.status_bar: QStatusBar = None

        # UI有効/無効化対象のウィジェットリスト
        self._ui_elements_to_disable: List[QWidget] = []

        self._initUI() # UIの初期化

        # 起動時にフォルダ選択ダイアログを表示
        self._select_initial_folder()

    def _setup_window_icon(self) -> None:
        """ウィンドウアイコンを設定します。"""
        # ここでアイコンファイルのパスを指定
        # icon_path = "path/to/your/icon.png"
        # if os.path.exists(icon_path):
        #     self.setWindowIcon(QIcon(icon_path))
        # else:
        #     logger.warning(f"Window icon not found at: {icon_path}")
        pass # アイコンがない場合は何もしない

    def _load_config(self) -> None:
        """設定ファイルから設定値を読み込み、メンバ変数に反映します。"""
        self._config_data = ConfigManager.load_config()
        self._current_folder = self._config_data.get(ConfigKeys.FOLDER) # 初期フォルダ
        self._thumbnail_columns = self._config_data.get(ConfigKeys.THUMBNAIL_COLUMNS, DEFAULT_CONFIG[ConfigKeys.THUMBNAIL_COLUMNS])
        self._cache_size = self._config_data.get(ConfigKeys.CACHE_SIZE, DEFAULT_CONFIG[ConfigKeys.CACHE_SIZE])
        self._current_sort = self._config_data.get(ConfigKeys.SORT_ORDER, DEFAULT_CONFIG[ConfigKeys.SORT_ORDER])
        self._preview_mode = self._config_data.get(ConfigKeys.PREVIEW_MODE, DEFAULT_CONFIG[ConfigKeys.PREVIEW_MODE])
        self._output_format = self._config_data.get(ConfigKeys.OUTPUT_FORMAT, DEFAULT_CONFIG[ConfigKeys.OUTPUT_FORMAT])
        logger.info("設定値をロードしました。")
        logger.debug(f"Loaded config: {self._config_data}")

    def _save_config(self) -> None:
        """現在の設定値を設定ファイルに保存します。"""
        # TreeView が非表示の場合、表示されていた時の列数に戻して保存する
        # (toggle_folder_tree で増減させているため)
        tree_visible = self.tree_view.isVisible()
        current_cols = self._thumbnail_columns
        if not tree_visible:
            cols_to_save = current_cols -1 if current_cols > MIN_THUMBNAIL_COLUMNS else MIN_THUMBNAIL_COLUMNS
        else:
            cols_to_save = current_cols

        self._config_data[ConfigKeys.FOLDER] = self._current_folder if self._current_folder else ""
        self._config_data[ConfigKeys.THUMBNAIL_COLUMNS] = cols_to_save
        self._config_data[ConfigKeys.CACHE_SIZE] = self._cache_size
        self._config_data[ConfigKeys.SORT_ORDER] = self._current_sort
        self._config_data[ConfigKeys.PREVIEW_MODE] = self._preview_mode
        self._config_data[ConfigKeys.OUTPUT_FORMAT] = self._output_format
        ConfigManager.save_config(self._config_data)
        logger.info("現在の設定値を保存しました。")

    # --- UI Initialization ---

    def _initUI(self) -> None:
        """UI要素の作成、レイアウト設定、シグナル接続を行います。"""
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)

        # 1. ウィジェットの作成
        self._create_widgets()

        # 2. レイアウトの設定
        self._setup_layouts(main_layout)

        # 3. シグナルとスロットの接続
        self._connect_signals()

        # 4. UI有効/無効化対象リストの作成
        self._populate_disable_list()

        # 5. ステータスバーの設定
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready.")

        logger.debug("UI initialization complete.")

    def _create_widgets(self) -> None:
        """UIで使われる主要なウィジェットを作成します。"""
        # トップバー
        self.config_button = QPushButton("Config")
        self.config_button.setFixedWidth(80)
        self.toggle_tree_button = QPushButton("<<")
        self.toggle_tree_button.setFixedWidth(40)
        self.toggle_tree_button.setToolTip("Toggle Folder Tree View")

        # フォルダツリー
        self.folder_model = QFileSystemModel()
        self.folder_model.setRootPath("") # ルートはシステム全体
        # PyQt6では QDir.Filter を使用
        self.folder_model.setFilter(QDir.Filter.Dirs | QDir.Filter.NoDotAndDotDot) # フォルダのみ表示
        self.tree_view = QTreeView()
        self.tree_view.setModel(self.folder_model)
        self.tree_view.setColumnWidth(0, 200) # 名前列の幅を調整
        self.tree_view.hideColumn(1) # サイズ非表示
        self.tree_view.hideColumn(2) # タイプ非表示
        self.tree_view.hideColumn(3) # 更新日時非表示
        self.tree_view.setHeaderHidden(True) # ヘッダー非表示 (シンプル化)

        # 画像エリア - 列数コントロール
        self.decrement_col_button = QPushButton("-")
        self.decrement_col_button.setFixedWidth(30)
        self.columns_display = QLineEdit(str(self._thumbnail_columns))
        self.columns_display.setFixedWidth(40)
        self.columns_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.columns_display.setReadOnly(True)
        self.increment_col_button = QPushButton("+")
        self.increment_col_button.setFixedWidth(30)

        # 画像エリア - フィルター
        self.filter_box = QLineEdit()
        self.filter_box.setPlaceholderText("Filter by keywords in metadata (comma separated)")
        self.filter_button = QPushButton("Filter")
        self.and_radio = QRadioButton("AND")
        self.or_radio = QRadioButton("OR")
        self.or_radio.setChecked(True)
        self.filter_mode_group = QButtonGroup(self)
        self.filter_mode_group.addButton(self.and_radio)
        self.filter_mode_group.addButton(self.or_radio)

        # 画像エリア - ソート
        self.filename_asc_radio = QPushButton("Filename ↑")
        self.filename_desc_radio = QPushButton("Filename ↓")
        self.date_asc_radio = QPushButton("Date ↑")
        self.date_desc_radio = QPushButton("Date ↓")
        # 各ボタンをCheckableに設定
        for btn in [self.filename_asc_radio, self.filename_desc_radio, self.date_asc_radio, self.date_desc_radio]:
            btn.setCheckable(True)
        # QButtonGroupで排他制御
        self.sort_group = QButtonGroup(self)
        self.sort_group.addButton(self.filename_asc_radio)
        self.sort_group.addButton(self.filename_desc_radio)
        self.sort_group.addButton(self.date_asc_radio)
        self.sort_group.addButton(self.date_desc_radio)
        # 初期ソート状態を設定
        self._update_sort_button_state()

        # 画像エリア - 選択コントロール
        self.select_all_button = QPushButton("Select All")
        self.unselect_button = QPushButton("Unselect All")
        self.copy_mode_button = QPushButton("Copy Mode")

        # サムネイル表示エリア
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff) # 水平スクロールバーを常に非表示
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft) # 左上詰めで配置
        self.grid_layout.setSpacing(5) # サムネイル間のスペース
        self.scroll_area.setWidget(self.grid_widget)

        # ボトムアクションボタン
        self.wc_creator_button = QPushButton("WC Creator")
        self.move_button = QPushButton("Move Selected")
        self.copy_button = QPushButton("Copy Selected")
        self.copy_button.setEnabled(False) # 初期状態は無効

        # スプリッター
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        logger.debug("Widgets created.")

    def _setup_layouts(self, main_layout: QVBoxLayout) -> None:
        """ウィジェットをレイアウトに配置します。"""
        # --- トップバー ---
        top_layout = QHBoxLayout()
        top_layout.addWidget(self.config_button)
        top_layout.addWidget(self.toggle_tree_button)
        top_layout.addStretch()
        main_layout.addLayout(top_layout)

        # --- メインエリア (スプリッター) ---
        # 左ペイン (フォルダツリー) - QWidgetでラップしてマージン設定可能に
        left_pane = QWidget()
        left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(0,0,0,0)
        left_layout.addWidget(self.tree_view)
        self.splitter.addWidget(left_pane)

        # 右ペイン (画像エリア)
        self.image_area_widget = QWidget()
        image_area_main_layout = QVBoxLayout(self.image_area_widget)

        # 画像エリア - コントロール部分
        controls_layout = QVBoxLayout()
        # -- 列数コントロール --
        col_layout = QHBoxLayout()
        col_layout.addStretch() # 右寄せにするためのスペーサー
        col_layout.addWidget(QLabel("Columns:"))
        col_layout.addWidget(self.decrement_col_button)
        col_layout.addWidget(self.columns_display)
        col_layout.addWidget(self.increment_col_button)
        controls_layout.addLayout(col_layout)

        # -- フィルター --
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(self.filter_box, 1) # Stretch factor 1
        filter_layout.addWidget(self.and_radio)
        filter_layout.addWidget(self.or_radio)
        filter_layout.addWidget(self.filter_button)
        controls_layout.addLayout(filter_layout)

        # -- ソート --
        sort_layout = QHBoxLayout()
        sort_layout.addWidget(QLabel("Sort by:"))
        sort_layout.addWidget(self.filename_asc_radio)
        sort_layout.addWidget(self.filename_desc_radio)
        sort_layout.addWidget(self.date_asc_radio)
        sort_layout.addWidget(self.date_desc_radio)
        sort_layout.addStretch()
        controls_layout.addLayout(sort_layout)

        # -- 選択コントロール --
        sel_layout = QHBoxLayout()
        sel_layout.addWidget(self.select_all_button)
        sel_layout.addWidget(self.unselect_button)
        sel_layout.addWidget(self.copy_mode_button)
        controls_layout.addLayout(sel_layout)

        image_area_main_layout.addLayout(controls_layout)

        # 画像エリア - サムネイルグリッド
        image_area_main_layout.addWidget(self.scroll_area, 1) # Stretch factor 1 で縦に伸長

        # 画像エリア - ボトムアクションボタン
        bottom_action_layout = QHBoxLayout()
        bottom_action_layout.addWidget(self.wc_creator_button)
        bottom_action_layout.addWidget(self.move_button)
        bottom_action_layout.addWidget(self.copy_button)
        image_area_main_layout.addLayout(bottom_action_layout)

        self.splitter.addWidget(self.image_area_widget)
        # 初期スプリッターサイズ比 (左:右 = 1:4 程度)
        self.splitter.setSizes([300, 1200])

        main_layout.addWidget(self.splitter, 1) # Stretch factor 1 で縦に伸長

        logger.debug("Layouts setup complete.")


    def _connect_signals(self) -> None:
        """UI要素のシグナルを対応するスロットに接続します。"""
        # トップバー
        self.config_button.clicked.connect(self.open_config_dialog)
        self.toggle_tree_button.clicked.connect(self.toggle_folder_tree)

        # フォルダツリー
        self.tree_view.clicked.connect(self._on_folder_selected_in_tree)

        # 列数コントロール
        self.decrement_col_button.clicked.connect(self.decrement_columns)
        self.increment_col_button.clicked.connect(self.increment_columns)

        # フィルター
        self.filter_button.clicked.connect(self.filter_images)
        self.filter_box.returnPressed.connect(self.filter_button.click) # Enterキーでフィルタ実行
        # ラジオボタンの変更は filter_images 内で状態を取得するので直接接続は不要

        # ソート
        self.filename_asc_radio.clicked.connect(lambda: self._sort_images_by_type(SORT_FILENAME_ASC))
        self.filename_desc_radio.clicked.connect(lambda: self._sort_images_by_type(SORT_FILENAME_DESC))
        self.date_asc_radio.clicked.connect(lambda: self._sort_images_by_type(SORT_DATE_ASC))
        self.date_desc_radio.clicked.connect(lambda: self._sort_images_by_type(SORT_DATE_DESC))

        # 選択コントロール
        self.select_all_button.clicked.connect(self.select_all_thumbnails)
        self.unselect_button.clicked.connect(self.unselect_all_thumbnails)
        self.copy_mode_button.clicked.connect(self.toggle_copy_mode)

        # ボトムアクション
        self.wc_creator_button.clicked.connect(self.open_wc_creator)
        self.move_button.clicked.connect(self.move_selected_images)
        self.copy_button.clicked.connect(self.copy_selected_images)

        logger.debug("Signals connected.")

    def _populate_disable_list(self) -> None:
        """非同期処理中に無効化するUI要素のリストを作成します。"""
        self._ui_elements_to_disable = [
            self.config_button, self.toggle_tree_button,
            self.tree_view, # ツリー自体も無効化
            self.decrement_col_button, self.increment_col_button,
            self.filter_box, self.filter_button, self.and_radio, self.or_radio,
            self.filename_asc_radio, self.filename_desc_radio,
            self.date_asc_radio, self.date_desc_radio,
            self.select_all_button, self.unselect_button, self.copy_mode_button,
            self.wc_creator_button, self.move_button, self.copy_button,
            # self.scroll_area # スクロール自体は許可しても良いかもしれない
        ]
        # QLineEdit (columns_display) は ReadOnly なので不要
        logger.debug(f"UI elements to disable list populated with {len(self._ui_elements_to_disable)} items.")

    def set_ui_enabled(self, enabled: bool) -> None:
        """
        指定されたUI要素リストの状態を有効または無効に設定します。

        Args:
            enabled: Trueで有効化、Falseで無効化。
        """
        logger.debug(f"Setting UI enabled state to: {enabled}")
        if not self._ui_elements_to_disable:
            logger.warning("UI elements to disable list is empty. Cannot change UI state.")
            return

        for widget in self._ui_elements_to_disable:
            # widget が None でないことを確認 (初期化途中など)
            if widget:
                widget.setEnabled(enabled)

        # コピーモードボタンの状態は特別に制御
        if self.copy_button:
            # UI有効化時はコピーモードの状態に応じて設定
            # UI無効化時は常に無効
            self.copy_button.setEnabled(enabled and self._copy_mode)
        if self.move_button:
            self.move_button.setEnabled(enabled and not self._copy_mode)
        if self.wc_creator_button:
             self.wc_creator_button.setEnabled(enabled and not self._copy_mode)


    # --- Core Application Logic ---

    def _select_initial_folder(self) -> None:
        """アプリケーション起動時にフォルダ選択ダイアログを表示します。"""
        initial_dir = self._current_folder if self._current_folder and os.path.isdir(self._current_folder) else ""
        folder = QFileDialog.getExistingDirectory(self, "Select Image Folder", initial_dir)
        if folder:
            self._current_folder = folder
            self._update_folder_tree_view(folder)
            self._load_images_from_folder(folder)
        else:
            # フォルダが選択されなかった場合 (ダイアログキャンセル)
            logger.warning("初期フォルダが選択されませんでした。")
            self.status_bar.showMessage("No folder selected. Please select a folder from the tree or use 'Config'.")
            # 必要であれば、再度ダイアログを表示するか、アプリを終了するなどの処理
            # self.close()

    def _load_images_from_folder(self, folder_path: str) -> None:
        """指定されたフォルダから画像を非同期で読み込みます。"""
        if not folder_path or not os.path.isdir(folder_path):
            logger.error(f"無効なフォルダパスが指定されました: {folder_path}")
            QMessageBox.warning(self, "Invalid Folder", f"Cannot load images from:\n{folder_path}")
            return

        logger.info(f"フォルダから画像の読み込みを開始します: {folder_path}")
        self.status_bar.showMessage(f"Loading images from {os.path.basename(folder_path)}...")
        self._current_folder = folder_path # 現在のフォルダを更新
        self._images = [] # 画像リストをクリア
        self._filtered_images = None # フィルター結果をクリア
        self.filter_box.clear() # フィルターボックスをクリア
        self._clear_thumbnail_grid() # サムネイル表示をクリア
        self.unselect_all_thumbnails() # 選択状態とコピーモード選択をクリア

        # UIを無効化
        self.set_ui_enabled(False)

        # 既存のローダーがあれば停止
        if self._image_loader and self._image_loader.isRunning():
            logger.debug("既存の ImageLoader を停止します...")
            self._image_loader.stop()
            logger.debug("既存の ImageLoader が停止しました。")

        # 新しいローダーを作成して開始
        self._image_loader = ImageLoader(folder_path, self._thumbnail_cache, DEFAULT_THUMBNAIL_SIZE)
        # シグナル接続
        self._image_loader.update_progress.connect(self._update_load_progress)
        # _add_thumbnail_widget を直接接続するのではなく、メインスレッドで処理するメソッドを介す
        self._image_loader.update_thumbnail.connect(self._handle_thumbnail_update)
        self._image_loader.finished_loading.connect(self._finalize_image_loading)
        self._image_loader.error_occurred.connect(self._handle_loader_error)
        self._image_loader.start() # スレッド開始

    # --- Progress/Status Update Slots ---
    def _update_load_progress(self, loaded_count: int, total_count: int) -> None:
        """ImageLoaderからの進捗更新シグナルを受け取るスロット。"""
        # logger.debug(f"Load progress: {loaded_count}/{total_count}")
        if total_count > 0:
            # パーセンテージ計算
            progress_percent = int((loaded_count / total_count) * 100)
            status_message = f"Loading images... {loaded_count}/{total_count} ({progress_percent}%)"
        else:
            # 合計が0の場合（または予期しない場合）
            status_message = f"Loading images... {loaded_count}/{total_count}"

        # ステータスバーにメッセージを表示
        self.status_bar.showMessage(status_message)
        # UIが固まるのを防ぐためにイベント処理を促す（大量のシグナル発行時）
        # QCoreApplication.processEvents() # 頻繁すぎると逆効果になる可能性もある

    def _handle_thumbnail_update(self, image_path: str, index: int) -> None:
        """ImageLoaderからサムネイル更新シグナルを受け取ったときの処理"""
        # このメソッドはメインスレッドで実行される
        # logger.debug(f"Received thumbnail update: {os.path.basename(image_path)} at index {index}")
        self._add_thumbnail_widget(image_path, index)

    def _add_thumbnail_widget(self, image_path: str, index: int) -> Optional[ImageThumbnail]:
        """指定された画像パスのサムネイルウィジェットを作成し、グリッドに追加します。"""
        try:
            thumb = ImageThumbnail(image_path, self._thumbnail_cache, self.grid_widget)
            # --- シグナル接続 ---
            # clicked シグナルにはサムネイル自身を渡すように lambda を使用
            thumb.clicked.connect(lambda checked, t=thumb: self._handle_thumbnail_click(t, checked))
            thumb.rightClicked.connect(lambda t=thumb: self._handle_thumbnail_right_click(t))
            thumb.doubleClicked.connect(lambda t=thumb: self._handle_thumbnail_double_click(t))

            row = index // self._thumbnail_columns
            col = index % self._thumbnail_columns
            self.grid_layout.addWidget(thumb, row, col)
            return thumb
        except Exception as e:
             logger.error(f"サムネイルウィジェットの追加中にエラー ({image_path}): {e}", exc_info=True)
             return None


    def _finalize_image_loading(self, loaded_image_paths: List[str]) -> None:
        """画像読み込み完了時の処理。"""
        logger.info(f"画像の読み込みが完了しました。{len(loaded_image_paths)} 件の画像がロードされました。")
        self._images = loaded_image_paths # ロードされたパスリストを保持
        # 読み込み完了後にソートを実行
        self._sort_images_by_type(self._current_sort, preserve_selection=False) # 初回ロード時は選択保持不要
        self.set_ui_enabled(True) # UIを有効化
        self.update_status_bar() # ステータスバー更新

        # 空フォルダチェック (オプション)
        if self._current_folder and send2trash:
            self._check_and_remove_empty_folders(self._current_folder)

    def _handle_loader_error(self, error_message: str) -> None:
        """ImageLoader でエラーが発生した場合の処理。"""
        logger.error(f"ImageLoader Error: {error_message}")
        self.status_bar.showMessage(f"Error loading images: {error_message}", 5000) # 5秒表示
        # UIを有効に戻す (エラーで停止した場合)
        if not self._image_loader or not self._image_loader.isRunning():
             self.set_ui_enabled(True)
        # エラー内容に応じて QMessageBox を表示することも検討
        # QMessageBox.warning(self, "Loading Error", error_message)

    def _clear_thumbnail_grid(self) -> None:
        """サムネイルグリッド内のすべてのウィジェットを削除します。"""
        logger.debug("Clearing thumbnail grid.")
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                # シグナルを切断してから削除 (メモリリーク対策)
                widget.disconnect()
                widget.deleteLater()
        # 内部の選択状態もクリア
        self._selection_order = []


    def _update_thumbnail_display(self, image_paths: List[str]) -> None:
        """
        指定された画像パスリストに基づいてサムネイルグリッドを更新します。
        既存の選択状態やコピーモードの順序はクリアされます。
        (ソートやフィルタリング後に使用)

        Args:
            image_paths: 表示する画像パスのリスト。
        """
        logger.info(f"Updating thumbnail display with {len(image_paths)} images.")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor) # 待機カーソル
        self.set_ui_enabled(False) # 更新中はUI無効化

        # 1. グリッドをクリアし、選択状態もリセット
        self._clear_thumbnail_grid()
        # self.unselect_all_thumbnails() # _clear_thumbnail_grid内で _selection_order はクリアされる

        # 2. 新しいサムネイルを追加
        for i, image_path in enumerate(image_paths):
             # メインスレッドがブロックされないように、少しずつ処理を進める (オプション)
             # QCoreApplication.processEvents()
             self._add_thumbnail_widget(image_path, i)

        self.set_ui_enabled(True) # UI有効化
        QApplication.restoreOverrideCursor() # カーソルを戻す
        self.update_status_bar() # ステータスバー更新
        logger.info("Thumbnail display updated.")


    def _update_folder_tree_view(self, folder_path: str) -> None:
        """指定されたフォルダがツリービューで見えるように設定します。"""
        logger.debug(f"Updating folder tree view for: {folder_path}")
        try:
            path = Path(folder_path)
            # ルートパスを必要に応じて設定（親フォルダが存在する場合）
            parent_path = path.parent
            if parent_path != self.folder_model.rootPath():
                 self.folder_model.setRootPath(str(parent_path))
                 logger.debug(f"Folder model root path set to: {parent_path}")

            # フォルダのインデックスを取得して選択状態にする
            folder_index = self.folder_model.index(folder_path)
            if folder_index.isValid():
                 # QTreeView の選択状態を設定
                 self.tree_view.setCurrentIndex(folder_index)
                 self.tree_view.scrollTo(folder_index, QTreeView.ScrollHint.PositionAtTop) # 見える位置にスクロール
                 # self.tree_view.expand(folder_index) # 展開は選択時に自動で行われる場合がある
                 logger.debug(f"Folder selected in tree view: {folder_path}")
            else:
                 logger.warning(f"Could not find index for folder in tree model: {folder_path}")
                 # モデルのルートパスを直接指定されたフォルダにリセットしてみる
                 self.folder_model.setRootPath(folder_path)


        except Exception as e:
            logger.error(f"フォルダツリービューの更新中にエラー: {e}", exc_info=True)

    # --- Event Handlers / Slots ---

    def _on_folder_selected_in_tree(self, index) -> None:
        """フォルダツリービューでフォルダがクリックされたときの処理。"""
        folder_path = self.folder_model.filePath(index)
        if folder_path and os.path.isdir(folder_path):
            logger.info(f"Folder selected in tree: {folder_path}")
            # 既に表示中のフォルダと同じなら何もしない (オプション)
            if folder_path == self._current_folder:
                 logger.debug("Selected folder is already loaded.")
                 return
            self._load_images_from_folder(folder_path)
        elif folder_path:
             logger.warning(f"Selected path is not a directory: {folder_path}")

    def open_config_dialog(self) -> None:
        """設定ダイアログを開きます。"""
        logger.debug("Opening Config dialog.")
        dialog = ConfigDialog(
            current_cache_size=self._cache_size,
            current_preview_mode=self._preview_mode,
            current_output_format=self._output_format,
            parent=self
        )
        # dialog.exec() を使うとモーダルで表示
        if dialog.exec(): # exec() は Accept の場合 True (1) を返す
             logger.info("Config dialog closed with Accept.")
             # update_config は ConfigDialog 内で呼ばれる
        else:
             logger.info("Config dialog closed with Reject or closed.")

    def update_config(self, new_cache_size: int, new_preview_mode: str, new_output_format: str) -> None:
        """ConfigDialogから設定変更通知を受け取ったときの処理。"""
        logger.info(f"Updating configuration: Cache={new_cache_size}, Preview='{new_preview_mode}', Output='{new_output_format}'")
        cache_changed = self._cache_size != new_cache_size
        self._cache_size = new_cache_size
        self._preview_mode = new_preview_mode
        self._output_format = new_output_format

        # キャッシュサイズが変更された場合、キャッシュをリサイズ
        if cache_changed:
            self._thumbnail_cache.resize(self._cache_size)

        # 設定をファイルに保存
        self._save_config()

        # ユーザーに変更を通知（ポップアップ）
        QMessageBox.information(self, "Settings Updated",
                            f"Settings have been updated:\n"
                            f"- Cache Size: {self._cache_size}\n"
                            f"- Preview Mode: {self._preview_mode.capitalize()}\n"
                            f"- Output Format: {self._output_format.replace('_', ' ').capitalize()}")

    def toggle_folder_tree(self) -> None:
        """フォルダツリービューの表示/非表示を切り替えます。"""
        if self.tree_view.isVisible():
            logger.debug("Hiding folder tree.")
            self.tree_view.hide()
            # スプリッターのサイズを調整して左ペインを隠す
            self.splitter.setSizes([0, self.splitter.sizes()[1]]) # 右ペインのサイズは維持
            self.toggle_tree_button.setText(">>")
            # 列数を増やす（スペースが広がるため）
            if self._thumbnail_columns < MAX_THUMBNAIL_COLUMNS:
                 self._thumbnail_columns += 1
                 self._update_columns_display()
                 self._update_thumbnail_grid_layout() # 再描画
        else:
            logger.debug("Showing folder tree.")
            self.tree_view.show()
            # スプリッターのサイズを元に戻す（またはデフォルト比率に）
            total_width = self.splitter.width()
            left_width = min(300, total_width // 4) # 最大300px or 1/4
            self.splitter.setSizes([left_width, total_width - left_width])
            self.toggle_tree_button.setText("<<")
            # 列数を減らす（スペースが狭くなるため）
            if self._thumbnail_columns > MIN_THUMBNAIL_COLUMNS:
                self._thumbnail_columns -= 1
                self._update_columns_display()
                self._update_thumbnail_grid_layout() # 再描画

    def decrement_columns(self) -> None:
        """サムネイル表示列数を減らします。"""
        if self._thumbnail_columns > MIN_THUMBNAIL_COLUMNS:
            self._thumbnail_columns -= 1
            self._update_columns_display()
            self._update_thumbnail_grid_layout()
            logger.debug(f"Thumbnail columns decremented to {self._thumbnail_columns}")

    def increment_columns(self) -> None:
        """サムネイル表示列数を増やします。"""
        if self._thumbnail_columns < MAX_THUMBNAIL_COLUMNS:
            self._thumbnail_columns += 1
            self._update_columns_display()
            self._update_thumbnail_grid_layout()
            logger.debug(f"Thumbnail columns incremented to {self._thumbnail_columns}")

    def _update_columns_display(self) -> None:
        """列数表示用LineEditの内容を更新します。"""
        self.columns_display.setText(str(self._thumbnail_columns))

    def _update_thumbnail_grid_layout(self) -> None:
        """サムネイルグリッドのレイアウトを現在の列数に合わせて更新します。"""
        logger.debug(f"Updating thumbnail grid layout for {self._thumbnail_columns} columns.")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.set_ui_enabled(False)

        widgets = []
        # レイアウトからウィジェットを削除し、リストに保持 (削除が重要)
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item is None: # アイテムがNoneの場合があるかもしれない
                 continue
            widget = item.widget()
            if widget:
                # ★★★ レイアウトから削除することを明示 ★★★
                # widget.setParent(None) # takeAt(0)で自動的に解除されるはずだが念のため
                widgets.append(widget)
            # else: レイアウトアイテムなどは無視

        # 新しい列数に基づいてウィジェットを再配置
        logger.debug(f"Re-adding {len(widgets)} widgets to grid with {self._thumbnail_columns} columns.")
        for i, widget in enumerate(widgets):
            row = i // self._thumbnail_columns
            col = i % self._thumbnail_columns
            # 再度レイアウトに追加
            self.grid_layout.addWidget(widget, row, col)

        # ★★★ レイアウトの更新を強制する (場合によっては必要) ★★★
        self.grid_layout.update()
        # self.grid_widget.updateGeometry() # ウィジェットのジオメトリ更新も促す

        self.set_ui_enabled(True)
        QApplication.restoreOverrideCursor()
        logger.debug("Thumbnail grid layout updated.")

    def filter_images(self) -> None:
        """フィルターボックスの入力に基づいて画像をフィルタリングします。"""
        query = self.filter_box.text().strip()
        if not query:
            self._clear_filter()
            return

        logger.info(f"Filtering images with query: '{query}'")
        self.status_bar.showMessage("Filtering images...")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.set_ui_enabled(False)

        terms = [term.strip().lower() for term in query.split(",") if term.strip()]
        filter_mode_and = self.and_radio.isChecked()
        matched_paths = []

        # 現在表示中の全画像リストを対象にする (フィルタがかかっていれば全画像に戻す)
        base_image_list = self._images # フィルタの元は常に全画像リスト

        # 存在する画像のみをフィルタリング対象に（より安全）
        valid_base_images = [img for img in base_image_list if os.path.exists(img)]
        if len(valid_base_images) < len(base_image_list):
             logger.warning(f"{len(base_image_list) - len(valid_base_images)} image files not found during filtering.")

        for image_path in valid_base_images:
            try:
                metadata_str = extract_metadata(image_path) # JSON文字列を取得
                # メタデータ文字列全体を検索対象とする (よりシンプルに)
                # TODO: 特定のキー(positive/negative/info)のみを対象にするか検討
                metadata_lower = metadata_str.lower()

                match = False
                if filter_mode_and:
                    # AND 条件: 全てのキーワードを含むか
                    match = all(term in metadata_lower for term in terms)
                else:
                    # OR 条件: いずれかのキーワードを含むか
                    match = any(term in metadata_lower for term in terms)

                if match:
                    matched_paths.append(image_path)

            except Exception as e:
                 logger.error(f"Error processing metadata for {image_path} during filter: {e}", exc_info=False)

        logger.info(f"Filtering complete. Found {len(matched_paths)} matching images.")
        self._filtered_images = matched_paths # フィルタ結果を保存
        # フィルタ結果に対して現在のソート順を適用して表示
        self._sort_images_by_type(self._current_sort, preserve_selection=False) # フィルタ後は選択解除

        QApplication.restoreOverrideCursor()
        self.set_ui_enabled(True)
        self.update_status_bar()

        if not matched_paths:
            QMessageBox.information(self, "Filter Result", "No matching images found for your query.")


    def _clear_filter(self) -> None:
        """フィルターをクリアし、全画像表示に戻します。"""
        if self._filtered_images is not None:
             logger.info("Clearing filter.")
             self.filter_box.clear()
             self._filtered_images = None
             # 全画像に対して現在のソート順を適用して表示
             self._sort_images_by_type(self._current_sort, preserve_selection=False) # フィルタクリア後は選択解除
             self.update_status_bar()
        else:
             logger.debug("Filter already clear.")

    def _get_current_image_list(self) -> List[str]:
        """現在表示対象となっている画像パスのリストを返します（フィルタ適用中ならフィルタ結果、そうでなければ全画像）。"""
        return self._filtered_images if self._filtered_images is not None else self._images

    def _sort_images_by_type(self, sort_type: str, preserve_selection: bool = True) -> None:
        """指定されたタイプで画像をソートし、表示を更新します。"""
        logger.info(f"Sorting images by: {sort_type}")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.set_ui_enabled(False)

        self._current_sort = sort_type
        self._update_sort_button_state() # ボタンのチェック状態を更新

        images_to_sort = self._get_current_image_list().copy() # ソート対象のリストを取得

        # --- 選択状態の保存 (preserve_selection=True の場合) ---
        selected_paths_before: Set[str] = set()
        selection_order_before: List[Tuple[str, int]] = [] # (path, order)
        if preserve_selection:
             current_widgets = self._get_all_thumbnail_widgets()
             for thumb in current_widgets:
                 if thumb.selected:
                      selected_paths_before.add(thumb.image_path)
                      if self._copy_mode and thumb.order > 0:
                           selection_order_before.append((thumb.image_path, thumb.order))
             # コピーモードの順序をソートしておく
             selection_order_before.sort(key=lambda item: item[1])
             logger.debug(f"Preserving selection: {len(selected_paths_before)} items.")
             if self._copy_mode:
                  logger.debug(f"Preserving copy order: {selection_order_before}")

        # --- ソートの実行 ---
        try:
            # 存在するファイルのみを対象にソートキーを取得
            sort_keys: Dict[str, Any] = {}
            valid_images_for_sort: List[str] = []
            for img_path in images_to_sort:
                 if os.path.exists(img_path):
                      valid_images_for_sort.append(img_path)
                      if sort_type == SORT_FILENAME_ASC or sort_type == SORT_FILENAME_DESC:
                           sort_keys[img_path] = os.path.basename(img_path).lower()
                      elif sort_type == SORT_DATE_ASC or sort_type == SORT_DATE_DESC:
                           sort_keys[img_path] = os.path.getmtime(img_path)
                 else:
                      logger.warning(f"ソート中にファイルが見つかりません: {img_path}")

            reverse_sort = sort_type == SORT_FILENAME_DESC or sort_type == SORT_DATE_DESC
            # sort_keys を使ってソート
            sorted_images = sorted(valid_images_for_sort, key=lambda p: sort_keys.get(p), reverse=reverse_sort)

        except Exception as e:
            logger.error(f"ソート中にエラーが発生しました: {e}", exc_info=True)
            QMessageBox.warning(self, "Sort Error", f"An error occurred during sorting:\n{e}")
            sorted_images = images_to_sort # エラー時は元の順序を維持

        # ソート結果を内部状態に反映
        if self._filtered_images is not None:
            self._filtered_images = sorted_images
        else:
            self._images = sorted_images

        # --- サムネイル表示の更新 ---
        self._clear_thumbnail_grid() # グリッドをクリア
        self._selection_order = [] # コピーモードの選択順序もクリア

        new_thumbnail_widgets: Dict[str, ImageThumbnail] = {} # path -> widget map

        for i, image_path in enumerate(sorted_images):
            thumb = self._add_thumbnail_widget(image_path, i)
            if thumb:
                 new_thumbnail_widgets[image_path] = thumb

        # --- 選択状態の復元 (preserve_selection=True の場合) ---
        if preserve_selection:
             restored_selection_count = 0
             restored_order_count = 0
             temp_selection_order = [None] * len(selection_order_before) # 順序復元用

             for path, thumb in new_thumbnail_widgets.items():
                  if path in selected_paths_before:
                       thumb.set_selected_visuals(True) # 見た目を選択状態に
                       restored_selection_count += 1
                       # コピーモードの順序も復元
                       if self._copy_mode:
                            found_order = False
                            for original_path, original_order in selection_order_before:
                                 if original_path == path:
                                      # 順序ラベルを設定し、内部リストの対応する位置に格納
                                      thumb.set_order_label(original_order)
                                      if 0 < original_order <= len(temp_selection_order):
                                           temp_selection_order[original_order - 1] = thumb
                                           restored_order_count += 1
                                      else:
                                           logger.warning(f"復元中に無効な順序番号 {original_order} が見つかりました for {path}")
                                      found_order = True
                                      break
                            if not found_order:
                                 # 順序リストにはなかったが選択はされていた場合 (通常モードからの切り替えなど)
                                 thumb.set_order_label(None) # 念のため非表示に
                  else:
                       thumb.set_selected_visuals(False)
                       thumb.set_order_label(None)

             # 復元した順序リストを確定 (None をフィルタリング)
             if self._copy_mode:
                  self._selection_order = [thumb for thumb in temp_selection_order if thumb is not None]
                  # 順序が飛んでいないかチェック (オプション)
                  if len(self._selection_order) != restored_order_count:
                       logger.warning("コピーモードの選択順序復元中に不整合が発生した可能性があります。")

             logger.debug(f"Selection restored: {restored_selection_count} items.")
             if self._copy_mode:
                  logger.debug(f"Copy order restored: {len(self._selection_order)} items.")

        QApplication.restoreOverrideCursor()
        self.set_ui_enabled(True)
        self.update_status_bar() # ステータスバー更新


    def _update_sort_button_state(self) -> None:
        """現在のソート順に基づいてソートボタンのチェック状態を更新します。"""
        buttons = {
            SORT_FILENAME_ASC: self.filename_asc_radio,
            SORT_FILENAME_DESC: self.filename_desc_radio,
            SORT_DATE_ASC: self.date_asc_radio,
            SORT_DATE_DESC: self.date_desc_radio
        }
        for sort_type, button in buttons.items():
             if button: # ボタンが存在するか確認
                 button.setChecked(self._current_sort == sort_type)

    def select_all_thumbnails(self) -> None:
        """表示されている全てのサムネイルを選択状態にします。"""
        logger.info("Selecting all thumbnails.")
        thumbnails = self._get_all_thumbnail_widgets()
        if not thumbnails: return

        # コピーモードでない場合
        if not self._copy_mode:
             for thumb in thumbnails:
                 thumb.set_selected_visuals(True)
        # コピーモードの場合
        else:
             self._selection_order = [] # 既存の選択順序をクリア
             for i, thumb in enumerate(thumbnails):
                 order = i + 1
                 thumb.set_selected_visuals(True)
                 thumb.set_order_label(order)
                 self._selection_order.append(thumb) # 新しい順序でリストに追加

        self.update_status_bar()

    def unselect_all_thumbnails(self) -> None:
        """表示されている全てのサムネイルの選択を解除します。"""
        logger.info("Unselecting all thumbnails.")
        thumbnails = self._get_all_thumbnail_widgets()
        if not thumbnails: return

        for thumb in thumbnails:
             thumb.set_selected_visuals(False)
             thumb.set_order_label(None) # 順序ラベルも消す

        # コピーモードの選択順序リストもクリア
        self._selection_order = []
        self.update_status_bar()

    def _get_selected_thumbnail_widgets(self) -> List[ImageThumbnail]:
         """現在選択されているサムネイルウィジェットのリストを取得します。"""
         # コピーモード時は _selection_order が選択リストとなる
         if self._copy_mode:
              # _selection_order には ImageThumbnail インスタンスが入っている
              return list(self._selection_order)
         # 通常モード時は、各サムネイルの selected 状態を確認
         else:
              selected_widgets = []
              for thumb in self._get_all_thumbnail_widgets():
                   # thumb.selected は MainWindow が管理しているので直接アクセスしない方が良い
                   # 代わりに、見た目 (スタイルシート) で判断するか、内部リストを別途持つ
                   # ここでは、MainWindow が set_selected_visuals で設定した _selected 状態を使う
                   # ※ _selected は ImageThumbnail の内部変数だが、便宜上アクセス
                   if thumb._selected: # ImageThumbnail 内部の _selected を参照
                        selected_widgets.append(thumb)
              return selected_widgets

    def _get_all_thumbnail_widgets(self) -> List[ImageThumbnail]:
        """グリッド内の全ての ImageThumbnail ウィジェットを取得します。"""
        widgets = []
        for i in range(self.grid_layout.count()):
            widget = self.grid_layout.itemAt(i).widget()
            if isinstance(widget, ImageThumbnail):
                widgets.append(widget)
        return widgets

    def toggle_copy_mode(self) -> None:
        """コピーモードの有効/無効を切り替えます。"""
        self._copy_mode = not self._copy_mode
        logger.info(f"Copy mode {'enabled' if self._copy_mode else 'disabled'}.")

        self.copy_mode_button.setText("Exit Copy Mode" if self._copy_mode else "Copy Mode")
        # ボタンの有効/無効状態を切り替え
        self.move_button.setEnabled(not self._copy_mode)
        self.copy_button.setEnabled(self._copy_mode)
        self.wc_creator_button.setEnabled(not self._copy_mode)

        # 既存の選択を全て解除
        self.unselect_all_thumbnails()
        # ステータスバー更新
        self.update_status_bar()


    def move_selected_images(self) -> None:
        """選択された画像を別フォルダに移動します。"""
        if self._copy_mode:
             logger.warning("Move operation is disabled in Copy Mode.")
             QMessageBox.warning(self, "Move Disabled", "Cannot move images while in Copy Mode.")
             return

        selected_widgets = self._get_selected_thumbnail_widgets()
        if not selected_widgets:
            QMessageBox.information(self, "No Selection", "Please select images to move.")
            return

        selected_paths = [thumb.image_path for thumb in selected_widgets]
        logger.info(f"Attempting to move {len(selected_paths)} images.")

        # 移動先フォルダを選択
        dest_folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder for Moving")
        if not dest_folder:
            logger.info("Move operation cancelled by user.")
            return

        # 移動処理の実行
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.set_ui_enabled(False)

        moved_count = 0
        renamed_files = []
        errors = []

        for image_path in selected_paths:
            base_name = os.path.basename(image_path)
            dest_path = os.path.join(dest_folder, base_name)
            counter = 1
            # 同名ファイルが存在する場合のリネーム処理
            while os.path.exists(dest_path):
                 name, ext = os.path.splitext(base_name)
                 new_base_name = f"{name}_{counter}{ext}"
                 dest_path = os.path.join(dest_folder, new_base_name)
                 counter += 1
                 if counter > 100: # 無限ループ防止
                      err_msg = f"Too many duplicates for {base_name} in destination folder."
                      logger.error(err_msg)
                      errors.append(f"{base_name}: {err_msg}")
                      dest_path = None # 移動を中止
                      break # このファイルの while ループを抜ける

            # 移動中止フラグが立っていない場合のみ移動
            if dest_path is None:
                 continue # 次のファイルの処理へ

            if counter > 1:
                renamed_files.append(os.path.basename(dest_path))

            # ファイル移動
            try:
                if os.path.exists(image_path): # 移動元が存在するか最終確認
                     logger.debug(f"Moving '{image_path}' to '{dest_path}'")
                     shutil.move(image_path, dest_path)
                     moved_count += 1
                else:
                     err_msg = f"Source file not found: {image_path}"
                     logger.warning(err_msg)
                     errors.append(f"{base_name}: Source not found")
            except Exception as e:
                err_msg = f"Error moving {base_name}: {e}"
                logger.error(err_msg, exc_info=True)
                errors.append(f"{base_name}: {e}")
                # エラーが発生しても処理を続ける

        QApplication.restoreOverrideCursor()
        self.set_ui_enabled(True)
        # ★★★ 修正箇所: copied_count を moved_count に ★★★
        logger.info(f"Move operation finished. Moved: {moved_count}, Renamed: {len(renamed_files)}, Errors: {len(errors)}")

        # --- 結果メッセージの表示 (変更済み部分) ---
        if not errors and not renamed_files:
             # エラーもリネームもない場合：ステータスバーに表示
             status_message = f"Moved {moved_count} image(s) successfully to {os.path.basename(dest_folder)}."
             self.status_bar.showMessage(status_message, 5000) # 5秒間表示
             logger.info(status_message)
        else:
             # エラーまたはリネームが発生した場合：ポップアップ表示
             message = f"Moved {moved_count} image(s) to {os.path.basename(dest_folder)}."
             details = []
             if renamed_files:
                 details.append("Renamed due to duplicates:\n- " + "\n- ".join(renamed_files))
             if errors:
                 details.append("Errors occurred during move:\n- " + "\n- ".join(errors))

             # ポップアップの詳細表示文字列を結合
             detail_str = ""
             if details:
                 detail_str = "\n\nDetails:\n" + "\n\n".join(details)

             QMessageBox.information(self, "Move Result", message + detail_str)
        # --------------------------------------

        # 移動元の画像リストをリロード
        if self._current_folder:
             logger.info("Reloading images from the source folder after move.")
             self._load_images_from_folder(self._current_folder)
        else:
             logger.warning("Cannot reload source folder: current folder path is not set.")

    def copy_selected_images(self) -> None:
        """
        コピーモードで選択された画像を、選択順に連番を付けて別フォルダにコピーします。
        コピー先に既存の連番ファイルがあれば、その続きの番号から開始します。
        """
        if not self._copy_mode:
             logger.warning("Copy operation is only available in Copy Mode.")
             QMessageBox.warning(self, "Copy Mode Required", "Please enable Copy Mode to copy images.")
             return

        if not self._selection_order:
            QMessageBox.information(self, "No Selection", "Please select images in order to copy.")
            return

        logger.info(f"Attempting to copy {len(self._selection_order)} images in selected order.")

        # コピー先フォルダを選択
        dest_folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder for Copying")
        if not dest_folder:
            logger.info("Copy operation cancelled by user.")
            return

        # --- コピー先フォルダの既存ファイルから次の連番を開始 ---
        next_number = 1
        logger.info(f"コピー先フォルダ '{dest_folder}' の既存ファイルを確認して連番を開始します。")
        try:
            # フォルダが存在するか確認
            if not os.path.isdir(dest_folder):
                 logger.error(f"コピー先フォルダが見つかりません: {dest_folder}")
                 QMessageBox.critical(self, "Error", f"Destination folder not found:\n{dest_folder}")
                 return

            existing_files = os.listdir(dest_folder)
            logger.debug(f"Found {len(existing_files)} items in destination folder.")
            existing_numbers = []
            pattern = re.compile(r"^(\d+)_") # 正規表現をコンパイル (行頭から数字+_にマッチ)

            for f_name in existing_files:
                 file_path = os.path.join(dest_folder, f_name)
                 # ファイルであること確認
                 if os.path.isfile(file_path):
                      logger.debug(f"Checking file for sequence number: {f_name}")
                      match = pattern.match(f_name) # コンパイルしたパターンでマッチ試行
                      if match:
                           try:
                               num_str = match.group(1)
                               num = int(num_str)
                               logger.debug(f"Found number {num} in filename '{f_name}'")
                               existing_numbers.append(num)
                           except ValueError:
                                logger.warning(f"Could not convert matched number '{num_str}' to int in file '{f_name}'")
                                continue # 数値変換失敗
                      else:
                           logger.debug(f"Filename '{f_name}' does not match the sequence pattern '^(\d+)_'.")
                 else:
                      logger.debug(f"Skipping item (not a file): {f_name}")

            if existing_numbers:
                 current_max = max(existing_numbers)
                 next_number = current_max + 1
                 logger.info(f"既存の最大連番は {current_max} です。次の番号 {next_number} から開始します。")
            else:
                 logger.info("既存の連番ファイルが見つかりませんでした。番号 1 から開始します。")

        except PermissionError as e:
             logger.error(f"コピー先フォルダへのアクセス権限がありません: {e}", exc_info=True)
             QMessageBox.critical(self, "Permission Error", f"Cannot access destination folder:\n{e}")
             return # 処理中断
        except Exception as e:
             logger.error(f"コピー先の既存ファイル番号の確認中に予期せぬエラーが発生しました: {e}", exc_info=True)
             QMessageBox.warning(self, "Warning", f"Could not determine the next sequence number due to an error. Starting from 1.\nError: {e}")
             next_number = 1 # エラー時は安全のため1から開始
        # ---------------------------------------------------------

        # --- コピー処理の実行 ---
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.set_ui_enabled(False)

        copied_count = 0
        errors = []

        for thumb in self._selection_order:
            image_path = thumb.image_path
            base_name = os.path.basename(image_path)
            new_filename = f"{next_number:03d}_{base_name}" # 3桁ゼロ埋め
            dest_path = os.path.join(dest_folder, new_filename)

            try:
                if os.path.exists(image_path):
                     logger.debug(f"Copying '{image_path}' to '{dest_path}'")
                     shutil.copy2(image_path, dest_path)
                     copied_count += 1
                     next_number += 1
                else:
                     err_msg = f"Source file not found: {image_path}"
                     logger.warning(err_msg)
                     errors.append(f"{base_name}: Source not found")
            except Exception as e:
                 err_msg = f"Error copying {base_name}: {e}"
                 logger.error(err_msg, exc_info=True)
                 errors.append(f"{base_name}: {e}")

        QApplication.restoreOverrideCursor()
        self.set_ui_enabled(True)
        logger.info(f"Copy operation finished. Copied: {copied_count}, Errors: {len(errors)}")

        # --- 結果メッセージの表示 ---
        message = f"Copied {copied_count} image(s) to {os.path.basename(dest_folder)} with sequential numbering."
        if errors:
            QMessageBox.warning(self, "Copy Result with Errors",
                                message + "\n\nErrors occurred:\n- " + "\n- ".join(errors))
        else:
            QMessageBox.information(self, "Copy Result", message)

        self.unselect_all_thumbnails()

    def show_metadata_dialog(self, image_path: str) -> None:
        """指定された画像のメタデータダイアログを表示または更新します。"""
        logger.debug(f"Showing metadata for: {image_path}")
        try:
            metadata = extract_metadata(image_path) # JSON文字列を取得
            if not self._metadata_dialog:
                logger.debug("Creating new MetadataDialog instance.")
                self._metadata_dialog = MetadataDialog(metadata, self)
                # モードレスで表示
                self._metadata_dialog.setModal(False)
                self._metadata_dialog.show()
            else:
                logger.debug("Updating existing MetadataDialog instance.")
                self._metadata_dialog.update_metadata(metadata)
                if not self._metadata_dialog.isVisible():
                     self._metadata_dialog.show()
                self._metadata_dialog.raise_() # 前面に表示
                self._metadata_dialog.activateWindow() # アクティブにする
        except Exception as e:
            logger.error(f"メタデータダイアログの表示中にエラー: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Could not display metadata:\n{e}")

    def open_wc_creator(self) -> None:
        """選択された画像でWC Creatorダイアログを開きます。"""
        if self._copy_mode:
             logger.warning("WC Creator is disabled in Copy Mode.")
             QMessageBox.warning(self, "WC Creator Disabled", "Cannot open WC Creator while in Copy Mode.")
             return

        selected_widgets = self._get_selected_thumbnail_widgets()
        if not selected_widgets:
            QMessageBox.information(self, "No Selection", "Please select images to use with WC Creator.")
            return

        selected_paths = [thumb.image_path for thumb in selected_widgets]
        logger.info(f"Opening WC Creator with {len(selected_paths)} images.")

        try:
            dialog = WCCreatorDialog(
                selected_images=selected_paths,
                thumbnail_cache=self._thumbnail_cache,
                output_format=self._output_format,
                parent=self
            )
            dialog.exec() # モーダルで表示
            logger.info("WC Creator dialog closed.")
        except Exception as e:
            logger.error(f"WC Creatorダイアログの表示中にエラー: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Could not open WC Creator:\n{e}")

    def _check_and_remove_empty_folders(self, folder: str) -> None:
        """指定されたフォルダ内の空のサブフォルダを検索し、ゴミ箱に移動するか確認します。"""
        if not send2trash:
             logger.warning("send2trash is not available. Skipping empty folder check.")
             return

        logger.info(f"Checking for empty subfolders in: {folder}")
        empty_folders_found = []
        try:
             # os.walk でサブフォルダを探索
             for root, dirs, files in os.walk(folder):
                 # dirs[:] を変更すると walk の挙動が変わるため、コピーしてイテレート
                 for d in list(dirs):
                      dir_path = os.path.join(root, d)
                      try:
                           # os.listdir が空かどうかで判定
                           if not os.listdir(dir_path):
                                empty_folders_found.append(dir_path)
                                # os.walk がそのフォルダに入らないように削除
                                dirs.remove(d)
                           # else:
                               # logger.debug(f"Folder not empty: {dir_path}")
                      except OSError as e:
                           logger.warning(f"Could not access or list directory {dir_path}: {e}")
                           # アクセスできないフォルダはスキップ
                           try:
                                dirs.remove(d)
                           except ValueError:
                                pass # 既に削除されている場合

        except Exception as e:
             logger.error(f"Error during empty folder check: {e}", exc_info=True)
             QMessageBox.warning(self, "Error", f"An error occurred while checking for empty folders:\n{e}")
             return

        if not empty_folders_found:
             logger.info("No empty subfolders found.")
             return

        logger.info(f"Found {len(empty_folders_found)} empty subfolders.")
        # 各空フォルダについて確認・削除
        deleted_count = 0
        for dir_path in empty_folders_found:
             # 確認ダイアログを表示 (現状維持の動作)
             reply = QMessageBox.question(self, '空のフォルダが見つかりました',
                                          f' "{dir_path}" は空です\nゴミ箱に移動しますか?',
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No) # デフォルトはNo

             if reply == QMessageBox.StandardButton.Yes:
                  try:
                       normalized_path = os.path.normpath(dir_path)
                       if normalized_path.startswith('\\\\?\\'):
                            path_to_send = normalized_path[4:] # プレフィックスを除去
                            logger.debug(f"Removed '\\\\?\\' prefix. Path to send: {path_to_send}")
                       else:
                            path_to_send = normalized_path

                       # send2trash はパスを適切に処理してくれるはず
                       logger.info(f"空フォルダを削除しました: {path_to_send}")
                       send2trash(path_to_send) # 正規化されたパスを渡す
                       deleted_count += 1
                  except ProcessLookupError as ple:
                       # 具体的なエラーを捕捉し、パスが見つからない旨をユーザーに伝える
                       error_msg = f"Failed to move folder '{dir_path}' to trash:\nThe specified path was not found by the system.\nError: {ple}"
                       logger.error(error_msg, exc_info=True)
                       QMessageBox.warning(self, "Deletion Error", error_msg)
                  except Exception as e:
                       error_msg = f"Failed to move folder '{dir_path}' to trash: {e}"
                       logger.error(error_msg, exc_info=True)
                       QMessageBox.warning(self, "Deletion Error", error_msg)

        if deleted_count > 0:
             logger.info(f"Moved {deleted_count} empty folders to trash.")
             # 必要であれば完了メッセージ
             # QMessageBox.information(self, "Empty Folders Removed", f"Moved {deleted_count} empty folders to trash.")


    def update_status_bar(self) -> None:
        """ステータスバーの表示を現在の状態に合わせて更新します。"""
        total_count = len(self._get_current_image_list())
        selected_count = len(self._get_selected_thumbnail_widgets())

        status_text = f"Total: {total_count} images"
        if self._copy_mode:
            status_text += f" | Copy Mode Enabled (Selected: {len(self._selection_order)})"
        else:
            status_text += f" | Selected: {selected_count}"

        if self._filtered_images is not None:
             status_text += " (Filtered)"

        self.status_bar.showMessage(status_text)
        # logger.debug(f"Status bar updated: {status_text}")


    # --- Thumbnail Interaction Handlers (Slots for ImageThumbnail signals) ---

    def _handle_thumbnail_click(self, thumbnail: ImageThumbnail, new_checked_state: bool) -> None:
        """ImageThumbnailのclickedシグナルを受け取るスロット。"""
        # 注意: new_checked_state は ImageThumbnail が内部で反転させた状態だが、
        # MainWindow が状態を管理するため、ここでは thumbnail インスタンスを使う。
        logger.debug(f"Thumbnail clicked: {os.path.basename(thumbnail.image_path)}")

        if self._copy_mode:
            # --- コピーモード時の処理 ---
            is_currently_selected = thumbnail in self._selection_order

            if is_currently_selected:
                # 選択解除
                logger.debug("Removing from copy selection order.")
                self._selection_order.remove(thumbnail)
                thumbnail.set_selected_visuals(False)
                thumbnail.set_order_label(None)
                # 順序の再割り当て
                for i, thumb in enumerate(self._selection_order, start=1):
                    thumb.set_order_label(i)
            else:
                # 新規選択
                logger.debug("Adding to copy selection order.")
                self._selection_order.append(thumbnail)
                order = len(self._selection_order)
                thumbnail.set_selected_visuals(True)
                thumbnail.set_order_label(order)
        else:
            # --- 通常モード時の処理 ---
            # 単純に選択状態を反転させる
            current_selected_state = thumbnail._selected # 内部状態を参照
            thumbnail.set_selected_visuals(not current_selected_state)

        # ステータスバーを更新
        self.update_status_bar()


    def _handle_thumbnail_right_click(self, thumbnail: ImageThumbnail) -> None:
        """ImageThumbnailのrightClickedシグナルを受け取るスロット。"""
        logger.debug(f"Thumbnail right-clicked: {os.path.basename(thumbnail.image_path)}")
        self.show_metadata_dialog(thumbnail.image_path)


    def _handle_thumbnail_double_click(self, thumbnail: ImageThumbnail) -> None:
        """ImageThumbnailのdoubleClickedシグナルを受け取るスロット。"""
        logger.debug(f"Thumbnail double-clicked: {os.path.basename(thumbnail.image_path)}")
        try:
             # 現在表示中のリストと、クリックされた画像のインデックスを取得
             current_list = self._get_current_image_list()
             if thumbnail.image_path in current_list:
                  initial_index = current_list.index(thumbnail.image_path)
                  # ImageDialog を表示 (引数を変更後の形式に合わせる)
                  dialog = ImageDialog(
                       all_image_paths=current_list,
                       current_index=initial_index,
                       preview_mode=self._preview_mode,
                       parent=self
                  )
                  dialog.exec()
             else:
                  logger.warning("Double-clicked image not found in the current list.")
                  # 単一画像でダイアログを開くフォールバック
                  dialog = ImageDialog([thumbnail.image_path], 0, self._preview_mode, self)
                  dialog.exec()

        except Exception as e:
             logger.error(f"画像ダイアログの表示中にエラー: {e}", exc_info=True)
             QMessageBox.critical(self, "Error", f"Could not open image preview:\n{e}")


    # --- Window Events ---

    def closeEvent(self, event: QCloseEvent) -> None:
        """ウィンドウが閉じられるときのイベント。設定を保存します。"""
        logger.info("Close event received. Saving configuration.")
        # 既存の ImageLoader が動作中なら停止を試みる
        if self._image_loader and self._image_loader.isRunning():
             logger.info("Stopping active ImageLoader before closing...")
             self._image_loader.stop() # スレッドの終了を待つ
             logger.info("ImageLoader stopped.")

        # メタデータダイアログが開いていれば閉じる
        if self._metadata_dialog and self._metadata_dialog.isVisible():
            self._metadata_dialog.close()

        self._save_config() # 設定を保存
        super().closeEvent(event) # デフォルトの閉じる処理を実行

    def restart_application(self):
        """アプリケーションを再起動します。"""
        logger.info("Restarting application...")
        self.close() # 現在のウィンドウを閉じる (closeEvent が呼ばれる)
        # 新しいプロセスを開始
        QProcess.startDetached(sys.executable, sys.argv)