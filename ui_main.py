# ui_main.py
import os
import sys
import json
import shutil
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QStatusBar, QTreeView, QSplitter, QGridLayout, QLineEdit, QLabel, QScrollArea,
    QButtonGroup, QRadioButton, QMessageBox
)
from PyQt6.QtCore import Qt, QProcess
from PyQt6.QtGui import QFileSystemModel
from modules.thumbnail_cache import ThumbnailCache
from modules.image_loader import ImageLoader
from modules.config import ConfigDialog, ConfigManager
from modules.metadata import extract_metadata
from modules.thumbnail_widget import ImageThumbnail
from modules.image_dialog import MetadataDialog

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Move/Copy Application")
        self.setGeometry(100, 100, 1500, 800)
        # 初期状態の変数設定
        self.images = []                # 読み込んだ画像のパスリスト
        self.copy_mode = False          # コピー（複数選択）モードか否か
        self.selection_order = []       # コピー時の選択順序を保持
        self.filter_results = []        # フィルター適用後の画像リスト
        self.thumbnail_columns = 5      # サムネイル表示の列数
        self.ui_state_saved = False     # UI状態保存フラグ
        self.ui_state = {}              # UI状態記憶用辞書
        self.current_sort = "filename_asc"  # 初期のソート順
        self.preview_mode = "seamless"       # 画像プレビュー表示モード
        self.output_format = "separate_lines"  # 出力フォーマットの初期値
        # 設定ファイルから値をロード
        self.config_data = ConfigManager.load_config()
        self.current_folder = self.config_data.get("folder", "")
        self.thumbnail_columns = self.config_data.get("thumbnail_columns", 5)
        self.cache_size = self.config_data.get("cache_size", 1000)
        self.current_sort = self.config_data.get("sort_order", "filename_asc")
        self.preview_mode = self.config_data.get("preview_mode", "seamless")
        self.output_format = self.config_data.get("output_format", "separate_lines")
        self.thumbnail_cache = ThumbnailCache(max_size=self.cache_size)
        self.image_loader = None
        self.metadata_dialog = None  # MetadataDialog のインスタンスを保持

        self.initUI()

    def initUI(self):
        # 中央ウィジェットとメインレイアウト
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)

        # 上部の設定ボタンとツリービューのトグルボタン
        top_layout = QHBoxLayout()
        self.config_button = QPushButton("Config")
        self.config_button.setFixedWidth(80)
        self.config_button.clicked.connect(self.open_config_dialog)
        self.toggle_button = QPushButton("<<")
        self.toggle_button.setFixedWidth(40)
        self.toggle_button.clicked.connect(self.toggle_folder_tree)
        top_layout.addWidget(self.config_button)
        top_layout.addWidget(self.toggle_button)
        top_layout.addStretch()
        main_layout.addLayout(top_layout)

        # QSplitter を使い、左にフォルダツリービュー、右に画像表示エリアを配置
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.splitter)

        # ── フォルダツリービュー ──
        self.folder_model = QFileSystemModel()
        self.folder_model.setRootPath("")
        self.tree_view = QTreeView()
        self.tree_view.setModel(self.folder_model)
        if self.current_folder:
            parent_folder = os.path.dirname(self.current_folder)
            self.folder_model.setRootPath(parent_folder)
            self.tree_view.setRootIndex(self.folder_model.index(parent_folder))
        self.tree_view.setColumnWidth(0, 150)
        self.tree_view.setColumnWidth(1, 60)
        self.tree_view.setColumnWidth(2, 50)
        self.tree_view.setColumnWidth(3, 100)
        self.tree_view.clicked.connect(self.on_folder_selected)
        self.splitter.addWidget(self.tree_view)

        # ── 画像表示エリア ──
        self.image_area_widget = QWidget()
        image_layout = QVBoxLayout(self.image_area_widget)

        # サムネイルの列数調整用コントロール（「-」「+」ボタン）
        col_layout = QHBoxLayout()
        self.decrement_button = QPushButton("-")
        self.decrement_button.clicked.connect(self.decrement_columns)
        self.columns_display = QLineEdit(str(self.thumbnail_columns))
        self.columns_display.setFixedWidth(40)
        self.columns_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.columns_display.setReadOnly(True)
        self.increment_button = QPushButton("+")
        self.increment_button.clicked.connect(self.increment_columns)
        col_layout.addWidget(self.decrement_button)
        col_layout.addWidget(self.columns_display)
        col_layout.addWidget(self.increment_button)
        image_layout.addLayout(col_layout)

        # フィルター機能：テキストボックス、Filter ボタン、and/or のラジオボタン
        filter_layout = QHBoxLayout()
        self.filter_box = QLineEdit()
        self.filter_box.setPlaceholderText("Enter filter keywords, separated by commas")
        self.filter_button = QPushButton("Filter")
        self.filter_button.clicked.connect(self.filter_images)
        self.filter_box.returnPressed.connect(self.filter_button.click)
        # ここを QPushButton から QRadioButton に変更
        self.and_radio = QRadioButton("and")
        self.or_radio = QRadioButton("or")
        self.or_radio.setChecked(True)
        # QButtonGroup でグループ化（相互排他にする）
        self.filter_mode_group = QButtonGroup(self)
        self.filter_mode_group.addButton(self.and_radio)
        self.filter_mode_group.addButton(self.or_radio)
        filter_layout.addWidget(self.filter_box)
        filter_layout.addWidget(self.and_radio)
        filter_layout.addWidget(self.or_radio)
        filter_layout.addWidget(self.filter_button)
        image_layout.addLayout(filter_layout)

        # ソート機能：ファイル名、更新日などの昇順／降順選択ボタン
        sort_layout = QHBoxLayout()
        self.filename_asc_radio = QPushButton("Filename ↑")
        self.filename_asc_radio.setCheckable(True)
        self.filename_desc_radio = QPushButton("Filename ↓")
        self.filename_desc_radio.setCheckable(True)
        self.date_asc_radio = QPushButton("Date ↑")
        self.date_asc_radio.setCheckable(True)
        self.date_desc_radio = QPushButton("Date ↓")
        self.date_desc_radio.setCheckable(True)
        self.sort_group = QButtonGroup(self)
        self.sort_group.addButton(self.filename_asc_radio)
        self.sort_group.addButton(self.filename_desc_radio)
        self.sort_group.addButton(self.date_asc_radio)
        self.sort_group.addButton(self.date_desc_radio)
        if self.current_sort == "filename_asc":
            self.filename_asc_radio.setChecked(True)
        elif self.current_sort == "filename_desc":
            self.filename_desc_radio.setChecked(True)
        elif self.current_sort == "date_asc":
            self.date_asc_radio.setChecked(True)
        elif self.current_sort == "date_desc":
            self.date_desc_radio.setChecked(True)
        self.filename_asc_radio.clicked.connect(lambda: self.sort_images("filename_asc"))
        self.filename_desc_radio.clicked.connect(lambda: self.sort_images("filename_desc"))
        self.date_asc_radio.clicked.connect(lambda: self.sort_images("date_asc"))
        self.date_desc_radio.clicked.connect(lambda: self.sort_images("date_desc"))
        sort_layout.addWidget(QLabel("Sort by:"))
        sort_layout.addWidget(self.filename_asc_radio)
        sort_layout.addWidget(self.filename_desc_radio)
        sort_layout.addWidget(self.date_asc_radio)
        sort_layout.addWidget(self.date_desc_radio)
        sort_layout.addStretch()
        image_layout.addLayout(sort_layout)

        # 選択／全選択／コピー・移動モード用ボタン
        sel_layout = QHBoxLayout()
        self.select_all_button = QPushButton("Select All")
        self.select_all_button.clicked.connect(self.select_all)
        self.unselect_button = QPushButton("Unselect All")
        self.unselect_button.clicked.connect(self.unselect_all)
        self.copy_mode_button = QPushButton("Copy Mode")
        self.copy_mode_button.clicked.connect(self.toggle_copy_mode)
        sel_layout.addWidget(self.select_all_button)
        sel_layout.addWidget(self.unselect_button)
        sel_layout.addWidget(self.copy_mode_button)
        image_layout.addLayout(sel_layout)

        # サムネイル表示用のスクロールエリア（グリッドレイアウト）
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.scroll_area.setWidget(self.grid_widget)
        image_layout.addWidget(self.scroll_area)

        # 移動／コピー操作用ボタン
        move_copy_layout = QHBoxLayout()
        self.wc_creator_button = QPushButton("WC Creator")
        self.wc_creator_button.clicked.connect(self.open_wc_creator)
        self.move_button = QPushButton("Move")
        self.move_button.clicked.connect(self.move_images)
        self.copy_button = QPushButton("Copy")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self.copy_images)
        move_copy_layout.addWidget(self.wc_creator_button)
        move_copy_layout.addWidget(self.move_button)
        move_copy_layout.addWidget(self.copy_button)
        image_layout.addLayout(move_copy_layout)

        self.splitter.addWidget(self.image_area_widget)
        self.splitter.setSizes([250, 800])

        # ステータスバー
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # アプリ起動時は必ずフォルダ選択ダイアログを表示する
        # self.current_folder が空でなければ、そのフォルダを初期値に設定する
        self.load_images()

    def open_config_dialog(self):
        dialog = ConfigDialog(current_cache_size=self.cache_size,
                            current_preview_mode=self.preview_mode,
                            current_output_format=self.output_format,
                            parent=self)
        dialog.exec()

    def update_columns_display(self):
        self.columns_display.setText(str(self.thumbnail_columns))

    def decrement_columns(self):
        if self.thumbnail_columns > 1:
            self.thumbnail_columns -= 1
            self.update_columns_display()
            self.update_thumbnail_columns(self.thumbnail_columns)

    def increment_columns(self):
        if self.thumbnail_columns < 20:
            self.thumbnail_columns += 1
            self.update_columns_display()
            self.update_thumbnail_columns(self.thumbnail_columns)

    def toggle_folder_tree(self):
        if self.tree_view.isVisible():
            self.tree_view.hide()
            self.splitter.setSizes([0, 800])
            self.toggle_button.setText(">>")
            self.thumbnail_columns += 1
            self.update_columns_display()
            self.update_thumbnail_columns(self.thumbnail_columns)
        else:
            self.tree_view.show()
            self.splitter.setSizes([250, 800])
            self.toggle_button.setText("<<")
            if self.thumbnail_columns > 1:
                self.thumbnail_columns -= 1
                self.update_columns_display()
                self.update_thumbnail_columns(self.thumbnail_columns)
        if self.filter_results:
            self.clear_thumbnails()
            for i, image_path in enumerate(self.filter_results):
                thumb = ImageThumbnail(image_path, self.thumbnail_cache, self.grid_widget)
                self.grid_layout.addWidget(thumb, i // self.thumbnail_columns, i % self.thumbnail_columns)

    def update_thumbnail_columns(self, columns):
        self.thumbnail_columns = columns
        self.clear_thumbnails()
        current_list = self.filter_results if self.filter_results else self.images
        for i, image_path in enumerate(current_list):
            thumb = ImageThumbnail(image_path, self.thumbnail_cache, self.grid_widget)
            self.grid_layout.addWidget(thumb, i // self.thumbnail_columns, i % self.thumbnail_columns)

    def clear_thumbnails(self):
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

    def sort_images(self, sort_type):
        self.current_sort = sort_type
        current_state = {}
        for i in range(self.grid_layout.count()):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                current_state[widget.image_path] = {"selected": widget.selected, "order": widget.order}
        images_to_sort = self.filter_results if self.filter_results else self.images
        
        # 存在するファイルのみを対象に
        valid_images = [img for img in images_to_sort if os.path.exists(img)]
        if len(valid_images) < len(images_to_sort):
            print(f"Missing files detected: {len(images_to_sort) - len(valid_images)} files not found")
        
        if sort_type == "filename_asc":
            sorted_images = sorted(valid_images, key=lambda x: os.path.basename(x).lower())
        elif sort_type == "filename_desc":
            sorted_images = sorted(valid_images, key=lambda x: os.path.basename(x).lower(), reverse=True)
        elif sort_type == "date_asc":
            sorted_images = sorted(valid_images, key=lambda x: os.path.getmtime(x))
        else:  # date_desc
            sorted_images = sorted(valid_images, key=lambda x: os.path.getmtime(x), reverse=True)
        
        self.clear_thumbnails()
        self.selection_order = []
        for i, image_path in enumerate(sorted_images):
            thumb = ImageThumbnail(image_path, self.thumbnail_cache, self.grid_widget)
            if image_path in current_state:
                state = current_state[image_path]
                if state['selected']:
                    thumb.selected = True
                    thumb.setStyleSheet("border: 3px solid orange;")
                    if self.copy_mode and state['order'] > 0:
                        thumb.order = state['order']
                        thumb.order_label.setText(str(thumb.order))
                        thumb.order_label.show()
                        while len(self.selection_order) < state['order']:
                            self.selection_order.append(None)
                        self.selection_order[state['order'] - 1] = thumb
            self.grid_layout.addWidget(thumb, i // self.thumbnail_columns, i % self.thumbnail_columns)
        if self.filter_results:
            self.filter_results = sorted_images
        else:
            self.images = sorted_images

    def save_last_values(self):
        if not self.tree_view.isVisible():
            self.thumbnail_columns = self.thumbnail_columns - 1
        self.config_data["folder"] = self.current_folder
        self.config_data["thumbnail_columns"] = self.thumbnail_columns
        self.config_data["cache_size"] = self.cache_size
        self.config_data["sort_order"] = self.current_sort
        self.config_data["preview_mode"] = self.preview_mode
        self.config_data["output_format"] = self.output_format
        ConfigManager.save_config(self.config_data)

    def update_config(self, new_cache_size, new_preview_mode, new_output_format):
        self.cache_size = new_cache_size
        self.preview_mode = new_preview_mode
        self.output_format = new_output_format
        self.save_last_values()
        QMessageBox.information(self, "Settings Updated",
                            f"Cache size: {new_cache_size}\n"
                            f"Preview mode: {new_preview_mode}\n"
                            f"Output format: {'Separate lines' if new_output_format == 'separate_lines' else 'Inline [:100]'}")

    def show_metadata_dialog(self, image_path):
        metadata = extract_metadata(image_path)
        if not self.metadata_dialog:
            self.metadata_dialog = MetadataDialog(metadata, self)
            self.metadata_dialog.setModal(False)
            self.metadata_dialog.show()
        else:
            self.metadata_dialog.update_metadata(metadata)
            if not self.metadata_dialog.isVisible():
                self.metadata_dialog.show()

    def closeEvent(self, event):
        # アプリケーション終了時にダイアログも閉じる
        if self.metadata_dialog:
            self.metadata_dialog.close()
        self.save_last_values()
        super().closeEvent(event)

    def on_folder_selected(self, index):
        folder_path = self.folder_model.filePath(index)
        self.filter_results = []  # フィルタ結果をクリア
        self.filter_box.clear()   # フィルタ入力欄をクリア
        self.load_images_from_folder(folder_path)

    def set_ui_enabled(self, enabled):
        if enabled:
            if self.ui_state_saved:
                for widget, state in self.ui_state.items():
                    widget.setEnabled(state)
                self.ui_state.clear()
                self.ui_state_saved = False
            else:
                for widget in self.findChildren(QWidget):
                    if widget != self.copy_button:
                        widget.setEnabled(True)
        else:
            if not self.ui_state:
                self.ui_state = {widget: widget.isEnabled() for widget in self.findChildren(QWidget)}
                self.ui_state_saved = True
            for widget in self.findChildren(QWidget):
                widget.setEnabled(False)

    def load_images_from_folder(self, folder):
        self.status_bar.showMessage("Loading images...")
        self.clear_thumbnails()
        self.set_ui_enabled(False)
        if self.image_loader:
            self.image_loader.stop()
        self.image_loader = ImageLoader(folder, self.thumbnail_cache)
        self.image_loader.update_progress.connect(self.update_image_count)
        self.image_loader.update_thumbnail.connect(self.add_thumbnail)
        self.image_loader.finished_loading.connect(self.finalize_loading)
        self.image_loader.start()

    def update_image_count(self, loaded, total):
        selected_count = sum(1 for i in range(self.grid_layout.count())
                             if self.grid_layout.itemAt(i).widget().selected)
        if not self.copy_mode:
            self.status_bar.showMessage(f"Total images: {total}, Selected images: {selected_count}")
        else:
            self.status_bar.showMessage(f"Total images: {total}")

    def update_selected_count(self):
        selected_count = sum(1 for i in range(self.grid_layout.count())
                             if self.grid_layout.itemAt(i).widget().selected)
        total_images = self.grid_layout.count()
        self.status_bar.showMessage(f"Total images: {total_images}, Selected images: {selected_count}")

    def add_thumbnail(self, image_path, index):
        thumb = ImageThumbnail(image_path, self.thumbnail_cache, self.grid_widget)
        self.grid_layout.addWidget(thumb, index // self.thumbnail_columns, index % self.thumbnail_columns)

    def finalize_loading(self, images):
        self.images = images
        self.sort_images(self.current_sort)  # sort_images は self.filter_results が空なら self.images を使用
        missing_files = [img for img in self.images if not os.path.exists(img)]
        if missing_files:
            self.status_bar.showMessage(f"Total images: {len(self.images)}, Missing files: {len(missing_files)}")
            print(f"Missing files: {missing_files}")
        else:
            self.status_bar.showMessage(f"Total images: {len(self.images)}")
        self.set_ui_enabled(True)
        if len(self.images) == 0:
            self.status_bar.showMessage("No images found. Please try again.")
            self.show_reload_button()

    def show_reload_button(self):
        reload_button = QPushButton("Reload")
        reload_button.setStyleSheet("background-color: lightgray; font-size: 16px;")
        reload_button.clicked.connect(self.load_images)
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        self.grid_layout.addWidget(reload_button, 0, 0, alignment=Qt.AlignmentFlag.AlignCenter)

    def select_all(self):
        for i in range(self.grid_layout.count()):
            thumb = self.grid_layout.itemAt(i).widget()
            if thumb and not thumb.selected:
                thumb.selected = True
                if self.copy_mode:
                    thumb.order = len(self.selection_order) + 1
                    self.selection_order.append(thumb)
                    thumb.order_label.setText(str(thumb.order))
                    thumb.order_label.show()
                thumb.setStyleSheet("border: 3px solid orange;")
        self.update_selected_count()

    def unselect_all(self):
        for i in range(self.grid_layout.count()):
            thumb = self.grid_layout.itemAt(i).widget()
            if thumb:
                thumb.selected = False
                thumb.setStyleSheet("")
                thumb.order = -1
                thumb.order_label.hide()
        self.selection_order = []
        self.update_selected_count()

    def check_and_remove_empty_folders(self, folder):
        from send2trash import send2trash
        for root, dirs, files in os.walk(folder):
            for dir in dirs:
                dir_path = os.path.join(root, dir)
                if not os.listdir(dir_path):  # 空フォルダの場合
                    reply = QMessageBox.question(self, '空のフォルダが見つかりました',
                                             f'フォルダ "{dir_path}" は空です。削除しますか?',
                                             QMessageBox.StandardButton.Yes | 
                                             QMessageBox.StandardButton.No, 
                                             QMessageBox.StandardButton.No)
                    if reply == QMessageBox.StandardButton.Yes:
                        normalized_path = os.path.normpath(dir_path.replace('\\\\?\\', ''))
                        try:
                            send2trash(normalized_path)  # ゴミ箱に移動
                        except Exception as e:
                            print(f"フォルダの削除中にエラーが発生しました: {e}")

    def load_images(self):
        # self.current_folder が空でなければ初期ディレクトリとして設定、なければデフォルト値（空文字列）を設定
        initial_dir = self.current_folder if self.current_folder else ""
        folder = QFileDialog.getExistingDirectory(self, "Select Image Folder", initial_dir)
        if folder:
            self.current_folder = folder
            parent_folder = os.path.dirname(folder)
            self.folder_model.setRootPath(parent_folder)
            self.tree_view.setRootIndex(self.folder_model.index(parent_folder))
            folder_index = self.folder_model.index(folder)
            self.tree_view.setCurrentIndex(folder_index)
            self.tree_view.expand(folder_index)
            self.check_and_remove_empty_folders(folder)
            self.load_images_from_folder(folder)


    def filter_images(self):
        query = self.filter_box.text()
        if not query:
            self.clear_filter()
            return
        self.status_bar.showMessage("Filtering...")
        self.filter_button.setEnabled(False)
        self.filter_box.setEnabled(False)
        terms = [term.strip() for term in query.split(",") if term.strip()]
        matches = []
        for image_path in self.images:
            metadata_str = extract_metadata(image_path)
            if self.and_radio.isChecked():
                if all(term.lower() in metadata_str.lower() for term in terms):
                    matches.append(image_path)
            else:
                if any(term.lower() in metadata_str.lower() for term in terms):
                    matches.append(image_path)
        self.filter_results = matches
        self.sort_images(self.current_sort)  # 現在のソート順を適用
        self.status_bar.clearMessage()
        self.filter_button.setEnabled(True)
        self.filter_box.setEnabled(True)

    def clear_filter(self):
        self.filter_results = []
        self.clear_thumbnails()
        for i, image_path in enumerate(self.images):
            thumb = ImageThumbnail(image_path, self.thumbnail_cache, self.grid_widget)
            self.grid_layout.addWidget(thumb, i // self.thumbnail_columns, i % self.thumbnail_columns)

    def toggle_copy_mode(self):
        self.copy_mode = not self.copy_mode
        self.copy_mode_button.setText("Copy Mode Exit" if self.copy_mode else "Copy Mode")
        self.move_button.setEnabled(not self.copy_mode)
        self.copy_button.setEnabled(self.copy_mode)
        self.wc_creator_button.setEnabled(not self.copy_mode)
        for i in range(self.grid_layout.count()):
            thumb = self.grid_layout.itemAt(i).widget()
            if thumb:
                thumb.selected = False
                thumb.setStyleSheet("")
                thumb.order = -1
                thumb.order_label.hide()
        if self.copy_mode:
            self.selection_order = []

    def move_images(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
        if not folder:
            return
        renamed_files = []
        selected_images = [self.grid_layout.itemAt(i).widget().image_path 
                        for i in range(self.grid_layout.count()) 
                        if self.grid_layout.itemAt(i).widget().selected]
        for image_path in selected_images:
            print(f"Moving: {image_path}")  # ログ追加
            base_name, ext = os.path.splitext(os.path.basename(image_path))
            new_path = os.path.join(folder, base_name + ext)
            counter = 1
            while os.path.exists(new_path):
                new_path = os.path.join(folder, f"{base_name}_{counter}{ext}")
                counter += 1
            try:
                os.rename(image_path, new_path)
                print(f"Moved to: {new_path}")  # ログ追加
            except Exception as e:
                print(f"Error moving {image_path}: {e}")
            if counter > 1:
                renamed_files.append(os.path.basename(new_path))
        self.unselect_all()
        # self.filter_box.clear() # フィルタ入力がクリア
        self.clear_thumbnails()
        self.image_loader = ImageLoader(self.image_loader.folder, self.thumbnail_cache)
        self.image_loader.update_progress.connect(self.update_image_count)
        self.image_loader.update_thumbnail.connect(self.add_thumbnail)
        self.image_loader.finished_loading.connect(self.finalize_loading)
        self.image_loader.start()
        self.check_and_remove_empty_folders(self.image_loader.folder)
        if renamed_files:
            QMessageBox.information(self, "Renamed Files",
                                    "Renamed due to duplicates:\n" + "\n".join(renamed_files))

    def copy_images(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
        if folder:
            existing_files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
            existing_numbers = []
            for f in existing_files:
                try:
                    num = int(f.split('_')[0])
                    existing_numbers.append(num)
                except ValueError:
                    continue
            next_number = max(existing_numbers, default=0) + 1
            for thumb in self.selection_order:
                image_path = thumb.image_path
                base_name = os.path.basename(image_path)
                new_path = os.path.join(folder, f"{next_number:03}_{base_name}")
                try:
                    shutil.copy2(image_path, new_path)
                except Exception as e:
                    print(f"Error copying {image_path}: {e}")
                next_number += 1
            self.unselect_all()

    def extract_metadata(self, image_path):
        return extract_metadata(image_path)
    

    def open_wc_creator(self):
        selected_images = [self.grid_layout.itemAt(i).widget().image_path 
                        for i in range(self.grid_layout.count()) 
                        if self.grid_layout.itemAt(i).widget().selected]
        
        if not selected_images:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No Selection", 
                            "Please select at least one image first.")
            return
        
        from modules.wc_creator import WCCreatorDialog
        dialog = WCCreatorDialog(selected_images, self.thumbnail_cache, self.output_format, self)
        dialog.exec()

    def restart_application(self):
        self.close()
        QProcess.startDetached(sys.executable, sys.argv)
