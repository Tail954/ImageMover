# g:\vscodeGit\modules\ui_manager.py
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTreeView, QSplitter,
    QGridLayout, QLineEdit, QLabel, QScrollArea, QButtonGroup, QRadioButton,
    QStatusBar, QApplication # QApplication をインポート
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFileSystemModel
from modules.thumbnail_widget import ImageThumbnail # update_selected_count で使う

class UIManager:
    """MainWindowのUI要素の作成、配置、シグナル接続、状態更新を担当するクラス"""

    def __init__(self, main_window, app_state):
        self.main_window = main_window
        self.app_state = app_state
        # UI状態保存用の変数をUIManagerに移動
        self.ui_state_saved = False
        self.ui_state = {}
        # サムネイル状態保存用辞書をUIManagerに移動
        self.saved_thumbnail_state = {}

    def setup_ui(self):
        """UI全体のセットアップを実行する"""
        # 中央ウィジェットとメインレイアウト
        main_layout = self._setup_main_layout()

        # 上部の設定ボタンとツリービューのトグルボタン
        top_layout = QHBoxLayout()
        self._setup_top_bar(top_layout)
        top_layout.addStretch()
        main_layout.addLayout(top_layout)

        # QSplitter
        self.main_window.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_window.splitter)

        self._setup_folder_tree()

        # 画像表示エリア
        image_layout = self._setup_image_area()
        self._setup_thumbnail_controls(image_layout)
        self._setup_filter_controls(image_layout)
        self._setup_sort_controls(image_layout)
        self._setup_selection_controls(image_layout)
        self._setup_thumbnail_grid(image_layout)
        self._setup_action_buttons(image_layout)
        self.main_window.splitter.addWidget(self.main_window.image_area_widget)
        self.main_window.splitter.setSizes([250, 800]) # 初期サイズ設定

        # ステータスバー
        self._setup_status_bar()

    # --- UI Setup Helper Methods ---
    def _setup_main_layout(self):
        """中央ウィジェットとメインレイアウトをセットアップ"""
        self.main_window.central_widget = QWidget()
        self.main_window.setCentralWidget(self.main_window.central_widget)
        main_layout = QVBoxLayout(self.main_window.central_widget)
        return main_layout

    def _setup_top_bar(self, top_layout):
        """トップバー（設定ボタン、トグルボタン）をセットアップ"""
        self.main_window.config_button = QPushButton("Config")
        self.main_window.config_button.setFixedWidth(80)
        self.main_window.toggle_button = QPushButton("<<")
        self.main_window.toggle_button.setFixedWidth(40)
        top_layout.addWidget(self.main_window.config_button)
        top_layout.addWidget(self.main_window.toggle_button)

    def _setup_folder_tree(self):
        """フォルダツリービューをセットアップ"""
        self.main_window.folder_model = QFileSystemModel()
        self.main_window.folder_model.setRootPath("")
        self.main_window.tree_view = QTreeView()
        self.main_window.tree_view.setModel(self.main_window.folder_model)
        # ActionHandler の current_folder を参照するように変更
        current_folder = None
        if hasattr(self.main_window, 'action_handler') and self.main_window.action_handler:
            current_folder = self.main_window.action_handler.current_folder

        if current_folder:
            parent_folder = os.path.dirname(current_folder)
            self.main_window.folder_model.setRootPath(parent_folder)
            self.main_window.tree_view.setRootIndex(self.main_window.folder_model.index(parent_folder))
        self.main_window.tree_view.setColumnWidth(0, 150)
        self.main_window.tree_view.setColumnWidth(1, 60)
        self.main_window.tree_view.setColumnWidth(2, 50)
        self.main_window.tree_view.setColumnWidth(3, 100)
        self.main_window.splitter.addWidget(self.main_window.tree_view)

    def _setup_image_area(self):
        """画像表示エリアのウィジェットとレイアウトをセットアップ"""
        self.main_window.image_area_widget = QWidget()
        image_layout = QVBoxLayout(self.main_window.image_area_widget)
        return image_layout

    def _setup_thumbnail_controls(self, image_layout):
        """サムネイル列数コントロールをセットアップ"""
        col_layout = QHBoxLayout()
        self.main_window.decrement_button = QPushButton("-")
        self.main_window.columns_display = QLineEdit(str(self.app_state.thumbnail_columns)) # AppState参照
        self.main_window.columns_display.setFixedWidth(40)
        self.main_window.columns_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_window.columns_display.setReadOnly(True)
        self.main_window.increment_button = QPushButton("+")
        col_layout.addWidget(self.main_window.decrement_button)
        col_layout.addWidget(self.main_window.columns_display)
        col_layout.addWidget(self.main_window.increment_button)
        image_layout.addLayout(col_layout)

    def _setup_filter_controls(self, image_layout):
        """フィルターコントロールをセットアップ"""
        filter_layout = QHBoxLayout()
        self.main_window.filter_box = QLineEdit()
        self.main_window.filter_box.setPlaceholderText("Enter filter keywords, separated by commas")
        self.main_window.filter_button = QPushButton("Filter")
        self.main_window.and_radio = QRadioButton("and")
        self.main_window.or_radio = QRadioButton("or")
        self.main_window.or_radio.setChecked(True)
        self.main_window.filter_mode_group = QButtonGroup(self.main_window) # 親をMainWindowに
        self.main_window.filter_mode_group.addButton(self.main_window.and_radio)
        self.main_window.filter_mode_group.addButton(self.main_window.or_radio)
        filter_layout.addWidget(self.main_window.filter_box)
        filter_layout.addWidget(self.main_window.and_radio)
        filter_layout.addWidget(self.main_window.or_radio)
        filter_layout.addWidget(self.main_window.filter_button)
        image_layout.addLayout(filter_layout)

    def _setup_sort_controls(self, image_layout):
        """ソートコントロールをセットアップ"""
        sort_layout = QHBoxLayout()
        self.main_window.filename_asc_radio = QPushButton("Filename ↑")
        self.main_window.filename_asc_radio.setCheckable(True)
        self.main_window.filename_desc_radio = QPushButton("Filename ↓")
        self.main_window.filename_desc_radio.setCheckable(True)
        self.main_window.date_asc_radio = QPushButton("Date ↑")
        self.main_window.date_asc_radio.setCheckable(True)
        self.main_window.date_desc_radio = QPushButton("Date ↓")
        self.main_window.date_desc_radio.setCheckable(True)
        self.main_window.sort_group = QButtonGroup(self.main_window) # 親をMainWindowに
        self.main_window.sort_group.addButton(self.main_window.filename_asc_radio)
        self.main_window.sort_group.addButton(self.main_window.filename_desc_radio)
        self.main_window.sort_group.addButton(self.main_window.date_asc_radio)
        self.main_window.sort_group.addButton(self.main_window.date_desc_radio)
        # 初期状態の設定 (AppState から取得)
        current_sort = self.app_state.current_sort
        if current_sort == "filename_asc": self.main_window.filename_asc_radio.setChecked(True)
        elif current_sort == "filename_desc": self.main_window.filename_desc_radio.setChecked(True)
        elif current_sort == "date_asc": self.main_window.date_asc_radio.setChecked(True)
        elif current_sort == "date_desc": self.main_window.date_desc_radio.setChecked(True)
        sort_layout.addWidget(QLabel("Sort by:"))
        sort_layout.addWidget(self.main_window.filename_asc_radio)
        sort_layout.addWidget(self.main_window.filename_desc_radio)
        sort_layout.addWidget(self.main_window.date_asc_radio)
        sort_layout.addWidget(self.main_window.date_desc_radio)
        sort_layout.addStretch()
        image_layout.addLayout(sort_layout)

    def _setup_selection_controls(self, image_layout):
        """選択コントロールをセットアップ"""
        sel_layout = QHBoxLayout()
        self.main_window.select_all_button = QPushButton("Select All")
        self.main_window.unselect_button = QPushButton("Unselect All")
        self.main_window.copy_mode_button = QPushButton("Copy Mode")
        sel_layout.addWidget(self.main_window.select_all_button)
        sel_layout.addWidget(self.main_window.unselect_button)
        sel_layout.addWidget(self.main_window.copy_mode_button)
        image_layout.addLayout(sel_layout)

    def _setup_thumbnail_grid(self, image_layout):
        """サムネイル表示用スクロールエリアとグリッドをセットアップ"""
        self.main_window.scroll_area = QScrollArea()
        self.main_window.scroll_area.setWidgetResizable(True)
        self.main_window.grid_widget = QWidget()
        self.main_window.grid_layout = QGridLayout(self.main_window.grid_widget)
        self.main_window.scroll_area.setWidget(self.main_window.grid_widget)
        image_layout.addWidget(self.main_window.scroll_area)

    def _setup_action_buttons(self, image_layout):
        """移動/コピー/D&D/WC Creatorボタンをセットアップ"""
        move_copy_layout = QHBoxLayout()
        self.main_window.wc_creator_button = QPushButton("WC Creator")
        self.main_window.move_button = QPushButton("Move")
        self.main_window.copy_button = QPushButton("Copy")
        self.main_window.copy_button.setEnabled(self.app_state.copy_mode) # AppState参照
        self.main_window.dnd_button = QPushButton("D&&D Window")
        self.main_window.dnd_button.setToolTip("画像ファイルをドラッグ＆ドロップしてメタデータを表示するウィンドウを開きます")
        move_copy_layout.addWidget(self.main_window.wc_creator_button)
        move_copy_layout.addWidget(self.main_window.move_button)
        move_copy_layout.addWidget(self.main_window.copy_button)
        move_copy_layout.addWidget(self.main_window.dnd_button)
        image_layout.addLayout(move_copy_layout)

    def _setup_status_bar(self):
        """ステータスバーをセットアップ"""
        self.main_window.status_bar = QStatusBar()
        self.main_window.setStatusBar(self.main_window.status_bar)

    def _connect_signals(self):
        """ウィジェットのシグナルとActionHandlerのメソッドを接続"""
        mw = self.main_window
        if not hasattr(mw, 'action_handler') or mw.action_handler is None:
            print("Error: ActionHandler not initialized when connecting signals.")
            return
        ah = mw.action_handler

        # Top bar
        if hasattr(mw, 'config_button'): mw.config_button.clicked.connect(ah.open_config_dialog)
        if hasattr(mw, 'toggle_button'): mw.toggle_button.clicked.connect(ah.toggle_folder_tree)
        # Folder tree
        if hasattr(mw, 'tree_view'): mw.tree_view.clicked.connect(ah.on_folder_selected)
        # Thumbnail controls
        if hasattr(mw, 'decrement_button'): mw.decrement_button.clicked.connect(ah.decrement_columns)
        if hasattr(mw, 'increment_button'): mw.increment_button.clicked.connect(ah.increment_columns)
        # Filter controls
        if hasattr(mw, 'filter_button'): mw.filter_button.clicked.connect(ah.filter_images)
        if hasattr(mw, 'filter_box'): mw.filter_box.returnPressed.connect(mw.filter_button.click)
        # Sort controls
        if hasattr(mw, 'filename_asc_radio'): mw.filename_asc_radio.clicked.connect(lambda: ah.sort_images("filename_asc"))
        if hasattr(mw, 'filename_desc_radio'): mw.filename_desc_radio.clicked.connect(lambda: ah.sort_images("filename_desc"))
        if hasattr(mw, 'date_asc_radio'): mw.date_asc_radio.clicked.connect(lambda: ah.sort_images("date_asc"))
        if hasattr(mw, 'date_desc_radio'): mw.date_desc_radio.clicked.connect(lambda: ah.sort_images("date_desc"))
        # Selection controls
        if hasattr(mw, 'select_all_button'): mw.select_all_button.clicked.connect(ah.select_all)
        if hasattr(mw, 'unselect_button'): mw.unselect_button.clicked.connect(ah.unselect_all)
        if hasattr(mw, 'copy_mode_button'): mw.copy_mode_button.clicked.connect(ah.toggle_copy_mode)
        # Action buttons
        if hasattr(mw, 'wc_creator_button'): mw.wc_creator_button.clicked.connect(ah.open_wc_creator)
        if hasattr(mw, 'move_button'): mw.move_button.clicked.connect(ah.move_images)
        if hasattr(mw, 'copy_button'): mw.copy_button.clicked.connect(ah.copy_images)
        if hasattr(mw, 'dnd_button'): mw.dnd_button.clicked.connect(ah.open_drop_window)

    # --- UI State/Update Methods ---

    def set_ui_enabled(self, enabled):
        """UI要素の有効/無効を切り替える"""
        mw = self.main_window
        widgets_to_manage = []
        # ウィジェットの存在を確認しながらリストに追加
        if hasattr(mw, 'config_button'): widgets_to_manage.append(mw.config_button)
        if hasattr(mw, 'toggle_button'): widgets_to_manage.append(mw.toggle_button)
        if hasattr(mw, 'tree_view'): widgets_to_manage.append(mw.tree_view)
        if hasattr(mw, 'decrement_button'): widgets_to_manage.append(mw.decrement_button)
        if hasattr(mw, 'columns_display'): widgets_to_manage.append(mw.columns_display)
        if hasattr(mw, 'increment_button'): widgets_to_manage.append(mw.increment_button)
        if hasattr(mw, 'filter_box'): widgets_to_manage.append(mw.filter_box)
        if hasattr(mw, 'filter_button'): widgets_to_manage.append(mw.filter_button)
        if hasattr(mw, 'and_radio'): widgets_to_manage.append(mw.and_radio)
        if hasattr(mw, 'or_radio'): widgets_to_manage.append(mw.or_radio)
        if hasattr(mw, 'filename_asc_radio'): widgets_to_manage.append(mw.filename_asc_radio)
        if hasattr(mw, 'filename_desc_radio'): widgets_to_manage.append(mw.filename_desc_radio)
        if hasattr(mw, 'date_asc_radio'): widgets_to_manage.append(mw.date_asc_radio)
        if hasattr(mw, 'date_desc_radio'): widgets_to_manage.append(mw.date_desc_radio)
        if hasattr(mw, 'select_all_button'): widgets_to_manage.append(mw.select_all_button)
        if hasattr(mw, 'unselect_button'): widgets_to_manage.append(mw.unselect_button)
        if hasattr(mw, 'copy_mode_button'): widgets_to_manage.append(mw.copy_mode_button)
        if hasattr(mw, 'wc_creator_button'): widgets_to_manage.append(mw.wc_creator_button)
        if hasattr(mw, 'move_button'): widgets_to_manage.append(mw.move_button)
        if hasattr(mw, 'copy_button'): widgets_to_manage.append(mw.copy_button)
        if hasattr(mw, 'dnd_button'): widgets_to_manage.append(mw.dnd_button)
        if hasattr(mw, 'scroll_area'): widgets_to_manage.append(mw.scroll_area)

        if enabled:
            if self.ui_state_saved:
                for widget, state in self.ui_state.items():
                    if widget in widgets_to_manage:
                        widget.setEnabled(state)
                self._update_action_buttons_state(self.app_state.copy_mode)
                self.ui_state.clear()
                self.ui_state_saved = False
            else:
                for widget in widgets_to_manage:
                    widget.setEnabled(True)
                self._update_action_buttons_state(self.app_state.copy_mode)
        else:
            if not self.ui_state_saved:
                self.ui_state = {widget: widget.isEnabled() for widget in widgets_to_manage if widget}
                self.ui_state_saved = True
            for widget in widgets_to_manage:
                 if widget: widget.setEnabled(False)

    def update_selected_count(self):
        """選択されている画像の数をステータスバーに表示"""
        mw = self.main_window
        if not hasattr(mw, 'grid_layout'): return
        selected_count = sum(1 for i in range(mw.grid_layout.count())
                             if isinstance(mw.grid_layout.itemAt(i).widget(), ImageThumbnail) and mw.grid_layout.itemAt(i).widget().selected)
        # ActionHandler 経由で image_data_manager を参照するように修正
        current_list_count = 0
        if hasattr(mw, 'action_handler') and mw.action_handler and hasattr(mw.action_handler, 'image_data_manager') and mw.action_handler.image_data_manager:
            current_list_count = len(mw.action_handler.image_data_manager.get_displayed_images())

        status_text = f"Total images: {current_list_count}"
        if hasattr(mw, 'filter_box') and mw.filter_box.text():
             status_text += f" (Filtered)"
        status_text += f", Selected images: {selected_count}"
        if hasattr(mw, 'status_bar'):
            mw.status_bar.showMessage(status_text)

    def update_image_count(self, loaded, total):
        """画像読み込みの進捗をステータスバーに表示"""
        mw = self.main_window
        if hasattr(mw, 'status_bar'):
            mw.status_bar.showMessage(f"Loading: {loaded}/{total}")

    def update_folder_tree_view(self, folder):
        """指定されたフォルダに基づいてツリービューを更新する"""
        mw = self.main_window
        if hasattr(mw, 'folder_model') and hasattr(mw, 'tree_view'):
            parent_folder = os.path.dirname(folder)
            mw.folder_model.setRootPath(parent_folder)
            root_index = mw.folder_model.index(parent_folder)
            mw.tree_view.setRootIndex(root_index)
            folder_index = mw.folder_model.index(folder)
            if folder_index.isValid():
                mw.tree_view.setCurrentIndex(folder_index)
                mw.tree_view.expand(folder_index)
                mw.tree_view.scrollTo(folder_index, QTreeView.ScrollHint.PositionAtTop)
            else:
                 print(f"Warning: Could not find index for folder: {folder}")

    def show_status_message(self, message, timeout=0):
        """ステータスバーにメッセージを表示する"""
        mw = self.main_window
        if hasattr(mw, 'status_bar'):
            mw.status_bar.showMessage(message, timeout)

    # --- Signal Handlers / Slots (Moved from MainWindow) ---

    def _handle_copy_mode_change(self, is_copy_mode):
        """AppStateのcopy_mode変更を受けてUIを更新"""
        mw = self.main_window
        if hasattr(mw, 'copy_mode_button'):
            mw.copy_mode_button.setText("Copy Mode Exit" if is_copy_mode else "Copy Mode")
        self._update_action_buttons_state(is_copy_mode)
        if hasattr(mw, 'action_handler') and mw.action_handler:
            mw.action_handler.unselect_all()
        self.update_selected_count()

    def _handle_thumbnail_columns_change(self, columns):
        """AppStateのthumbnail_columns変更を受けてUIを更新"""
        mw = self.main_window
        if hasattr(mw, 'columns_display'):
            mw.columns_display.setText(str(columns))
        # ThumbnailViewController と ImageDataManager は ActionHandler 経由でアクセス
        if hasattr(mw, 'action_handler') and mw.action_handler:
            ah = mw.action_handler
            if ah.thumbnail_view_controller and hasattr(mw, 'grid_layout'):
                current_state = {}
                for i in range(mw.grid_layout.count()):
                    widget = mw.grid_layout.itemAt(i).widget()
                    if widget and isinstance(widget, ImageThumbnail):
                        current_state[widget.image_path] = {"selected": widget.selected, "order": widget.order}
                self.saved_thumbnail_state = current_state
                # ActionHandler 経由で ImageDataManager のリストを取得
                image_list = ah.image_data_manager.get_displayed_images() if ah.image_data_manager else []
                ah.thumbnail_view_controller.update_display(
                    image_list,
                    columns,
                    self.saved_thumbnail_state,
                    self.app_state.copy_mode
                )

    # --- UI Update Methods (Moved from MainWindow) ---
    def _update_action_buttons_state(self, is_copy_mode):
        """コピーモードの状態に基づいてボタンの有効/無効を切り替える"""
        mw = self.main_window
        if hasattr(mw, 'move_button'):
            mw.move_button.setEnabled(not is_copy_mode)
        if hasattr(mw, 'copy_button'):
            mw.copy_button.setEnabled(is_copy_mode)
        if hasattr(mw, 'wc_creator_button'):
            mw.wc_creator_button.setEnabled(not is_copy_mode)

