import sys
import os
import json
import shutil
import piexif
from send2trash import send2trash
from PIL import Image
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QRadioButton, QLineEdit, QTextEdit, QDialog,
    QScrollArea, QWidget, QGridLayout, QButtonGroup, QStatusBar, QMessageBox,
    QTreeView, QSplitter,QGroupBox
)
from PyQt6.QtGui import QImage, QPixmap, QFileSystemModel
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QProcess
from pathlib import Path
import concurrent.futures
import threading
from functools import lru_cache

class ThumbnailCache:
    #サムネイルのキャッシュを管理するクラス
    def __init__(self, max_size=1000):
        self.cache = {}
        self.max_size = max_size
        self.lock = threading.Lock()

    #@lru_cache(maxsize=1000)
    def get_thumbnail(self, image_path, size):
        """キャッシュからサムネイルを取得、または新規作成"""
        cache_key = f"{image_path}_{size}"
        
        with self.lock:
            # キャッシュヒット
            if cache_key in self.cache:
                print(f"Cache hit: {image_path}")
                return self.cache[cache_key]

        # キャッシュミス時にサムネイルを生成
        print(f"Cache miss, generating thumbnail: {image_path}")
        try:
            image = QImage(image_path)
            pixmap = QPixmap.fromImage(image).scaled(
                size, size, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            # キャッシュに追加
            with self.lock:
                if len(self.cache) >= self.max_size:
                    oldest_key = next(iter(self.cache))
                    del self.cache[oldest_key]
                self.cache[cache_key] = pixmap
            
            return pixmap
        except Exception as e:
            print(f"Error creating thumbnail for {image_path}: {e}")
            return None

    def clear(self):
        """キャッシュをクリア"""
        with self.lock:
            self.cache.clear()

    def resize(self, new_max_size):
        """キャッシュサイズを変更"""
        with self.lock:
            self.max_size = new_max_size
            while len(self.cache) > self.max_size:
                self.cache.pop(next(iter(self.cache)))

class ImageLoader(QThread):
    #非同期で画像をロードするスレッド
    update_progress = pyqtSignal(int, int)
    update_thumbnail = pyqtSignal(str, int)
    finished_loading = pyqtSignal(list)

    def __init__(self, folder, thumbnail_cache, thumbnail_size=200):
        super().__init__()
        self.folder = folder
        self.thumbnail_size = thumbnail_size
        self.images = []
        self.total_files = 0
        self._is_running = True
        self.thumbnail_cache = thumbnail_cache  # 修正: キャッシュを外部から受け取る
        self.valid_extensions = {'.png', '.jpeg', '.jpg', '.webp'}

    def stop(self):
        #スレッドを停止
        self._is_running = False
        self.wait()  # スレッドの終了を待つ

    def is_valid_image(self, file_path):
        #ファイルが有効な画像かどうかチェック
        return Path(file_path).suffix.lower() in self.valid_extensions

    def run(self):
        #画像ロードの実行
        try:
            self.total_files = sum(
                1 for f in Path(self.folder).rglob('*')
                if self.is_valid_image(f)
            )

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                future_to_path = {
                    executor.submit(self.process_image, str(f)): str(f)
                    for f in Path(self.folder).rglob('*')
                    if self.is_valid_image(f)
                }

                for i, future in enumerate(concurrent.futures.as_completed(future_to_path)):
                    if not self._is_running:
                        break
                    
                    path = future_to_path[future]
                    try:
                        if future.result():
                            self.images.append(path)
                            self.update_thumbnail.emit(path, i)
                    except Exception as e:
                        print(f"Error processing {path}: {e}")

                    self.update_progress.emit(i + 1, self.total_files)

            if self._is_running:
                self.finished_loading.emit(self.images)

        except Exception as e:
            print(f"Error in image loader: {e}")

    def is_cached(self, image_path):
        return image_path in self.thumbnail_cache.cache
    
    def process_image(self, image_path):
        try:
            # キャッシュキーを生成
            cache_key = f"{image_path}_{self.thumbnail_size}"
            if cache_key in self.thumbnail_cache.cache:
                return True
            
            self.thumbnail_cache.get_thumbnail(image_path, self.thumbnail_size)
            return True
        except Exception as e:
            print(f"Error processing image {image_path}: {e}")
            return False

class MetadataDialog(QDialog):
    def __init__(self, metadata, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Metadata")

        # メタデータを辞書形式に変換
        metadata_dict = json.loads(metadata)

        self.positive_edit = QTextEdit(self)
        self.negative_edit = QTextEdit(self)
        self.others_edit = QTextEdit(self)

        self.positive_edit.setPlainText(metadata_dict.get("positive", "No positive metadata"))
        self.negative_edit.setPlainText(metadata_dict.get("negative", "No negative metadata"))
        self.others_edit.setPlainText(metadata_dict.get("others", "No other metadata"))

        self.positive_edit.setReadOnly(True)
        self.negative_edit.setReadOnly(True)
        self.others_edit.setReadOnly(True)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Positive"))
        layout.addWidget(self.positive_edit)
        layout.addWidget(QLabel("Negative"))
        layout.addWidget(self.negative_edit)
        layout.addWidget(QLabel("Other"))
        layout.addWidget(self.others_edit)
        self.setLayout(layout)
        self.setMinimumSize(400, 600)

class ImageDialog(QDialog):
    def __init__(self, image_path, preview_mode='seamless', parent=None):
        super().__init__(parent)
        self.setWindowTitle("Full Image")
        self.preview_mode = preview_mode
        self.scale_factor = 1.0
        self.saved_geometry = None  # サイズと位置を保存するための変数
        
        # レイアウトの初期化
        self.layout = QVBoxLayout()
        
        # 最大化ボタンを含むツールバーの作成（ホイールモード用）
        self.tool_layout = QHBoxLayout()
        self.tool_layout.addStretch()
        self.maximize_button = QPushButton("□")
        self.maximize_button.setFixedSize(30, 30)
        self.maximize_button.clicked.connect(self.toggle_maximize)
        self.tool_layout.addWidget(self.maximize_button)
        self.layout.addLayout(self.tool_layout)
        
        # 画像表示用のウィジェット
        if self.preview_mode == 'seamless':
            self.setup_seamless_mode(image_path)
        else:
            self.setup_wheel_mode(image_path)
            
        self.setLayout(self.layout)
        self.setMinimumSize(200, 200)
        
    def setup_seamless_mode(self, image_path):
        self.image_label = QLabel(self)
        self.pixmap = QPixmap(image_path)
        self.image_label.setPixmap(self.pixmap)
        self.layout.addWidget(self.image_label)
        
    def setup_wheel_mode(self, image_path):
        # スクロールエリアの設定
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        
        # 画像ラベルの設定
        self.image_label = QLabel()
        self.pixmap = QPixmap(image_path)
        self.image_label.setPixmap(self.pixmap)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # スクロールエリアに画像ラベルを設定
        self.scroll_area.setWidget(self.image_label)
        self.layout.addWidget(self.scroll_area)
        
        self.setToolTip("Ctrl + ホイールでズーム、ドラッグでスクロール")
        
        self.resize(1000,900)
        
    def wheelEvent(self, event):
        if self.preview_mode == 'wheel':
            # Ctrlキーが押されている場合のみズーム
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                delta = event.angleDelta().y()
                if delta > 0:
                    self.scale_factor *= 1.1
                else:
                    self.scale_factor *= 0.9
                
                # スケーリングした画像を表示
                scaled_pixmap = self.pixmap.scaled(
                    self.pixmap.size() * self.scale_factor,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.image_label.setPixmap(scaled_pixmap)
            else:
                # 通常のスクロール
                self.scroll_area.verticalScrollBar().setValue(
                    self.scroll_area.verticalScrollBar().value() - event.angleDelta().y()
                )
    
    # ウィンドウサイズ以上に拡大されていたらマウスドラッグでスクロール
    def mousePressEvent(self, event):
        if self.preview_mode == 'wheel' and (self.image_label.size().width() > self.size().width() or self.image_label.size().height() > self.size().height()):
            self.drag_start = event.pos()
            self.scroll_start_v = self.scroll_area.verticalScrollBar().value()
            self.scroll_start_h = self.scroll_area.horizontalScrollBar().value()

    def mouseMoveEvent(self, event):
        if self.preview_mode == 'wheel' and (self.image_label.size().width() > self.size().width() or self.image_label.size().height() > self.size().height()):
            delta = event.pos() - self.drag_start
            self.scroll_area.verticalScrollBar().setValue(self.scroll_start_v - delta.y())
            self.scroll_area.horizontalScrollBar().setValue(self.scroll_start_h - delta.x())

    def resizeEvent(self, event):
        if self.preview_mode == 'seamless':
            new_pixmap = self.pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.image_label.setPixmap(new_pixmap)
        else:
            super().resizeEvent(event)

    def toggle_maximize(self):
        # 現在のウィンドウサイズを取得
        current_size = self.size()
        # 現在のディスプレイ解像度を取得
        # ディスプレイ解像度に合わせてウィンドウサイズを変更
        screen = QApplication.primaryScreen()

        if self.windowState() != Qt.WindowState.WindowMaximized: 
            if self.saved_geometry is None:
                self.saved_geometry = self.saveGeometry()   

            self.setWindowState(Qt.WindowState.WindowMaximized)
            self.maximize_button.setText("❐")
        else:
            if self.saved_geometry:
                self.restoreGeometry(self.saved_geometry)
                self.setWindowState(Qt.WindowState.WindowNoState)
                self.maximize_button.setText("□")
                self.saved_geometry = None  # 記憶した情報をクリア

class ImageThumbnail(QLabel):
    def __init__(self, image_path, thumbnail_cache, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.thumbnail_cache = thumbnail_cache
        self.selected = False
        self.order = -1 # クリック順序を保持するプロパティ
        self.setFixedSize(200, 200)
        self.setScaledContents(False)  # アスペクト比を維持するためにFalseに設定
        
        QThread.currentThread().priority()
        self.load_thumbnail()
        
        self.setToolTip(os.path.dirname(image_path))

        # 番号を表示するためのラベルを追加
        self.order_label = QLabel(self)
        self.order_label.setStyleSheet("color: white; background-color: black;")
        self.order_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.order_label.setGeometry(0, 0, 30, 30)
        self.order_label.hide()

    def load_thumbnail(self):
        try:
            pixmap = self.thumbnail_cache.get_thumbnail(self.image_path, 200)
            if pixmap:
                self.setPixmap(pixmap)
            else:
                self.setText("Error")
        except Exception as e:
            print(f"Error loading thumbnail: {e}")
            self.setText("Failed to load thumbnail")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected = not self.selected
            main_window = self.window()
            while main_window and not isinstance(main_window, MainWindow):
                main_window = main_window.parent()
            if main_window:
                if main_window.copy_mode:
                    if self.selected:
                        self.order = len(main_window.selection_order) + 1
                        main_window.selection_order.append(self)
                        self.order_label.setText(str(self.order))
                        self.order_label.show()
                    else:
                        main_window.selection_order.remove(self)
                        self.order = -1
                        self.order_label.hide()
                        # クリック順序を更新
                        for i, thumbnail in enumerate(main_window.selection_order, start=1):
                            thumbnail.order = i
                            thumbnail.order_label.setText(str(i))
                else:
                    self.order = -1
                    self.order_label.hide()
                    main_window.update_selected_count()
            self.setStyleSheet("border: 3px solid orange;" if self.selected else "")
        elif event.button() == Qt.MouseButton.RightButton:
            main_window = self.window()
            while main_window and not isinstance(main_window, MainWindow):
                main_window = main_window.parent()
            if main_window:
                metadata = main_window.extract_metadata(self.image_path)
                dialog = MetadataDialog(metadata)
                dialog.exec()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            main_window = self.window()
            while main_window and not isinstance(main_window, MainWindow):
                main_window = main_window.parent()
            if main_window:
                dialog = ImageDialog(self.image_path, main_window.preview_mode, main_window)
                dialog.exec()

class ConfigDialog(QDialog):
    def __init__(self, current_cache_size, current_preview_mode='seamless', parent=None):
        super().__init__(parent)
        self.setWindowTitle("Config Settings")
        self.current_cache_size = current_cache_size
        self.current_preview_mode = current_preview_mode
        self.main_window = parent  # 親ウィンドウへの参照を保持
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)

        # キャッシュサイズ設定
        cache_group = QGroupBox("Cache Settings")
        cache_layout = QVBoxLayout()
        label = QLabel("Cache Size:")
        self.cache_size_input = QLineEdit(str(self.current_cache_size))
        cache_layout.addWidget(label)
        cache_layout.addWidget(self.cache_size_input)
        cache_group.setLayout(cache_layout)
        
        # 画像表示モード設定
        display_group = QGroupBox("Preview mode")
        display_layout = QVBoxLayout()
        self.seamless_radio = QRadioButton("シームレス")
        self.wheel_radio = QRadioButton("ホイール")
        if self.current_preview_mode == 'seamless':
            self.seamless_radio.setChecked(True)
        else:
            self.wheel_radio.setChecked(True)
        display_layout.addWidget(self.seamless_radio)
        display_layout.addWidget(self.wheel_radio)
        display_group.setLayout(display_layout)

        # 適用ボタン
        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(self.apply_changes)

        layout.addWidget(cache_group)
        layout.addWidget(display_group)
        layout.addWidget(apply_button)

    def apply_changes(self):
        try:
            new_cache_size = int(self.cache_size_input.text())
            preview_mode = 'seamless' if self.seamless_radio.isChecked() else 'wheel'
            # 親ウィンドウの参照を使用
            if self.main_window:
                self.main_window.update_config(new_cache_size, preview_mode)
                self.close()
            else:
                QMessageBox.warning(self, "Error", "Parent window not found.")
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter a valid number.")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Move/Copy Application")
        self.setGeometry(100, 100, 1500, 800)
        self.images = []
        self.copy_mode = False
        self.selection_order = []  # クリック順序を保持するリスト
        self.current_folder = ""   # 現在のフォルダパスを保持
        self.filter_results = []   # フィルタ結果を保持するリストを追加
        self.thumbnail_columns = 5  # サムネイルの列数を保持する変数を追加
        self.ui_state_saved = False  # UI状態が記憶されているかを示すフラグ
        self.ui_state = {}  # UI状態を記憶する辞書
        self.thumbnail_cache = ThumbnailCache()
        self.current_sort = "filename_asc"  # デフォルトのソート順
        self.preview_mode = 'seamless'  # デフォルト値を追加

        # キャッシュサイズとpreview_modeをlast_value.jsonからロード
        self.cache_size = 1000
        self.load_last_values()

        self.initUI()

    def initUI(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        layout = QVBoxLayout(self.central_widget)

        # Config button
        config_layout = QHBoxLayout()
        self.config_button = QPushButton("Config")
        self.config_button.setFixedWidth(50)
        self.config_button.clicked.connect(self.open_config_dialog)
        config_layout.addStretch()
        config_layout.addWidget(self.config_button)
        layout.addLayout(config_layout)

        # フォルダツリーの幅を０にするトグルボタンを追加
        self.toggle_button = QPushButton("<<")
        self.toggle_button.setFixedWidth(40)  # ボタンの幅を40に設定
        self.toggle_button.clicked.connect(self.toggle_folder_tree)
        layout.addWidget(self.toggle_button)

        # スプリッターを作成して、フォルダツリーと画像表示部分を分割
        self.splitter = QSplitter(self)
        layout.addWidget(self.splitter)

        # フォルダツリーを作成
        self.folder_model = QFileSystemModel()
        self.folder_model.setRootPath("")  # 初期化時は空文字列を設定
        self.folder_view = QTreeView()
        self.folder_view.setModel(self.folder_model)
        # 初期状態ではホームディレクトリを表示しない
        self.folder_view.setRootIndex(self.folder_model.index(""))
        self.folder_view.clicked.connect(self.on_folder_selected)

        # カラムの幅を設定
        self.folder_view.setColumnWidth(0, 150)  # Name列の幅
        self.folder_view.setColumnWidth(1, 60)    # Size列
        self.folder_view.setColumnWidth(2, 50)    # Type列
        self.folder_view.setColumnWidth(3, 100)    # Date Modified列

        # サムネイル表示エリアを作成
        self.image_area_widget = QWidget()
        image_layout = QVBoxLayout(self.image_area_widget)

        # サムネイルの列数を変更するためのコントロールを追加
        control_layout = QHBoxLayout()
        self.decrement_button = QPushButton("-")
        self.increment_button = QPushButton("+")
        self.columns_display = QLineEdit()
        self.columns_display.setFixedWidth(40)
        self.columns_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.columns_display.setReadOnly(True)
        self.update_columns_display()

        self.decrement_button.clicked.connect(self.decrement_columns)
        self.increment_button.clicked.connect(self.increment_columns)

        control_layout.addWidget(self.decrement_button)
        control_layout.addWidget(self.columns_display)
        control_layout.addWidget(self.increment_button)
        image_layout.addLayout(control_layout)

        # filter section
        filter_layout = QHBoxLayout()
        self.filter_box = QLineEdit()
        self.filter_button = QPushButton("Filter")
        self.filter_button.clicked.connect(self.filter_images)
        self.filter_box.returnPressed.connect(self.filter_button.click)
        self.and_radio = QRadioButton("and")
        self.or_radio = QRadioButton("or")
        self.or_radio.setChecked(True)
        self.radio_group = QButtonGroup()
        self.radio_group.addButton(self.and_radio)
        self.radio_group.addButton(self.or_radio)
        filter_layout.addWidget(self.filter_box)
        filter_layout.addWidget(self.and_radio)
        filter_layout.addWidget(self.or_radio)
        filter_layout.addWidget(self.filter_button)
        image_layout.addLayout(filter_layout)

        # Sort section
        sort_layout = QHBoxLayout()
        # Create sort radio buttons
        self.filename_asc_radio = QRadioButton("Filename ↑")
        self.filename_desc_radio = QRadioButton("Filename ↓")
        self.date_asc_radio = QRadioButton("Date ↑")
        self.date_desc_radio = QRadioButton("Date ↓")        
        # Group the radio buttons
        self.sort_group = QButtonGroup()
        self.sort_group.addButton(self.filename_asc_radio)
        self.sort_group.addButton(self.filename_desc_radio)
        self.sort_group.addButton(self.date_asc_radio)
        self.sort_group.addButton(self.date_desc_radio)        
        # Set initial radio button based on saved value
        if self.current_sort == "filename_asc":
            self.filename_asc_radio.setChecked(True)
        elif self.current_sort == "filename_desc":
            self.filename_desc_radio.setChecked(True)
        elif self.current_sort == "date_asc":
            self.date_asc_radio.setChecked(True)
        elif self.current_sort == "date_desc":
            self.date_desc_radio.setChecked(True)        
        # Connect radio buttons to sort function
        self.filename_asc_radio.toggled.connect(lambda: self.sort_images("filename_asc"))
        self.filename_desc_radio.toggled.connect(lambda: self.sort_images("filename_desc"))
        self.date_asc_radio.toggled.connect(lambda: self.sort_images("date_asc"))
        self.date_desc_radio.toggled.connect(lambda: self.sort_images("date_desc"))       
        # Add radio buttons to layout
        sort_layout.addWidget(QLabel("Sort by:"))
        sort_layout.addWidget(self.filename_asc_radio)
        sort_layout.addWidget(self.filename_desc_radio)
        sort_layout.addWidget(self.date_asc_radio)
        sort_layout.addWidget(self.date_desc_radio)
        sort_layout.addStretch()        
        # Add sort layout after filter layout
        image_layout.addLayout(sort_layout)

        # UnSelect, Select All, Copy mode, buttons
        button_layout = QHBoxLayout()
        self.select_all_button = QPushButton("Select All")
        self.select_all_button.clicked.connect(self.select_all)
        self.unselect_button = QPushButton("UnSelect All")
        self.unselect_button.clicked.connect(self.unselect_all)
        self.copy_mode_button = QPushButton("Copy Mode")
        self.copy_mode_button.clicked.connect(self.toggle_copy_mode)
        button_layout.addWidget(self.select_all_button)
        button_layout.addWidget(self.unselect_button)
        button_layout.addWidget(self.copy_mode_button)
        image_layout.addLayout(button_layout)

        # サムネイル表示エリア
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.scroll_area.setWidget(self.grid_widget)
        image_layout.addWidget(self.scroll_area)

        # Move/Copy buttons
        move_copy_layout = QHBoxLayout()
        self.move_button = QPushButton("Move")
        self.move_button.clicked.connect(self.move_images)
        self.copy_button = QPushButton("Copy")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self.copy_images)
        move_copy_layout.addWidget(self.move_button)
        move_copy_layout.addWidget(self.copy_button)
        layout.addLayout(move_copy_layout)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # スプリッターにフォルダツリーと画像表示エリアを追加
        self.splitter.addWidget(self.folder_view)
        self.splitter.addWidget(self.image_area_widget)
        self.splitter.setSizes([250, 800])  # 初期サイズを設定

        # Load images on startup
        self.load_images()

    def open_config_dialog(self):
        # ConfigDialogにself（MainWindow）を親として明示的に渡す
        dialog = ConfigDialog(
            current_cache_size=self.cache_size,
            current_preview_mode=self.preview_mode,
            parent=self
        )
        dialog.exec()

    def update_cache_size(self, new_cache_size):
        self.cache_size = new_cache_size
        self.save_last_values()
        QMessageBox.information(self, "Cache Size Updated", f"Cache size has been updated to {new_cache_size}.")

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
        if self.folder_view.isVisible():
            self.folder_view.hide()
            self.splitter.setSizes([0, 800])
            self.toggle_button.setText(">>")
            self.thumbnail_columns = self.thumbnail_columns + 1  # 列数を+1
            self.update_columns_display()
            self.update_thumbnail_columns(self.thumbnail_columns)
        else:
            self.folder_view.show()
            self.splitter.setSizes([250, 800])
            self.toggle_button.setText("<<")
            if self.thumbnail_columns > 1:
                self.thumbnail_columns = self.thumbnail_columns - 1   # 列数を-1
                self.update_columns_display()
                self.update_thumbnail_columns(self.thumbnail_columns)
                
        # フィルタ結果がある場合、それを再表示
        if self.filter_results:
            self.clear_thumbnails()
            #現在のサムネイルを全て削除する
            for i, image_path in enumerate(self.filter_results):
                thumbnail = ImageThumbnail(image_path, self.thumbnail_cache, self.grid_widget)
                self.grid_layout.addWidget(thumbnail, i // self.thumbnail_columns, 
                                         i % self.thumbnail_columns)
                
    # サムネイルの列数を更新する
    def update_thumbnail_columns(self, columns):
        self.thumbnail_columns = columns  # 列数を更新
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                self.grid_layout.removeWidget(widget)
        for i, image_path in enumerate(self.images):
            thumbnail = ImageThumbnail(image_path, self.thumbnail_cache, self.grid_widget)
            self.grid_layout.addWidget(thumbnail, i // self.thumbnail_columns, 
                                     i % self.thumbnail_columns)
     
     # サムネイルを全て削除する
    def clear_thumbnails(self):
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

    def sort_images(self, sort_type):
        self.current_sort = sort_type
        
        # Get current selection and order state
        current_state = {
            self.grid_layout.itemAt(i).widget().image_path: {
                'selected': self.grid_layout.itemAt(i).widget().selected,
                'order': self.grid_layout.itemAt(i).widget().order
            }
            for i in range(self.grid_layout.count())
        }
        
        # Sort images based on selected criteria
        images_to_sort = self.filter_results if self.filter_results else self.images
        
        if sort_type == "filename_asc":
            sorted_images = sorted(images_to_sort, key=lambda x: os.path.basename(x).lower())
        elif sort_type == "filename_desc":
            sorted_images = sorted(images_to_sort, key=lambda x: os.path.basename(x).lower(), reverse=True)
        elif sort_type == "date_asc":
            sorted_images = sorted(images_to_sort, key=lambda x: os.path.getmtime(x))
        else:  # date_desc
            sorted_images = sorted(images_to_sort, key=lambda x: os.path.getmtime(x), reverse=True)
        
        # Clear and rebuild thumbnails
        self.clear_thumbnails()
        
        # Reset selection order list but maintain the order information
        self.selection_order = []
        
        # Recreate thumbnails in sorted order
        for i, image_path in enumerate(sorted_images):
            thumbnail = ImageThumbnail(image_path, self.thumbnail_cache, self.grid_widget)
            
            # Restore selection state and order
            if image_path in current_state:
                state = current_state[image_path]
                if state['selected']:
                    thumbnail.selected = True
                    thumbnail.setStyleSheet("border: 3px solid orange;")
                    
                    # Restore copy mode order if in copy mode
                    if self.copy_mode and state['order'] > 0:
                        thumbnail.order = state['order']
                        thumbnail.order_label.setText(str(thumbnail.order))
                        thumbnail.order_label.show()
                        # Insert thumbnail at the correct position in selection_order
                        while len(self.selection_order) < state['order']:
                            self.selection_order.append(None)
                        self.selection_order[state['order'] - 1] = thumbnail
        
            self.grid_layout.addWidget(thumbnail, i // self.thumbnail_columns, 
                                    i % self.thumbnail_columns)
        
        # Clean up selection_order list by removing any None entries
        self.selection_order = [x for x in self.selection_order if x is not None]
        
        if self.filter_results:
            self.filter_results = sorted_images
        else:
            self.images = sorted_images

    # 最後に選択したフォルダをロードする
    def load_last_values(self):
        if os.path.exists("last_value.json"):
            with open("last_value.json", "r") as file:
                data = json.load(file)
                self.current_folder = data.get("folder", "")
                self.thumbnail_columns = data.get("thumbnail_columns", 5)
                self.cache_size = data.get("cache_size", 1000)
                self.current_sort = data.get("sort_order", "filename_asc")
                self.preview_mode = data.get("preview_mode", "seamless")

    # 最後に選択したフォルダを保存する
    def save_last_values(self):
        if not self.folder_view.isVisible():
            self.thumbnail_columns = self.thumbnail_columns - 1

        with open("last_value.json", "w") as file:
            json.dump({
                "folder": self.current_folder,
                "thumbnail_columns": self.thumbnail_columns,
                "cache_size": self.cache_size,
                "sort_order": self.current_sort,
                "preview_mode": self.preview_mode
            }, file)

    def update_config(self, new_cache_size, new_preview_mode):
        self.cache_size = new_cache_size
        self.preview_mode = new_preview_mode

        # 表示するモードに基づいてメッセージを設定
        if new_preview_mode == 'wheel':
            preview_mode_text = "ホイール"
        elif new_preview_mode == 'seamless':
            preview_mode_text = "シームレス"
        else:
            preview_mode_text = new_preview_mode  # それ以外のケースも考慮
    
        self.save_last_values()
        QMessageBox.information(self, "Settings Updated", 
                              f"Cache size: {new_cache_size}\nPreview mode: {preview_mode_text}")

    def closeEvent(self, event):
        self.save_last_values()
        super().closeEvent(event)

    # フォルダが選択されたときに呼び出されるスロット
    def on_folder_selected(self, index):
        folder_path = self.folder_model.filePath(index)
        self.load_images_from_folder(folder_path)

    def set_ui_enabled(self, enabled):
        """UI全体を有効化/無効化し、2回目以降のみ状態を記憶/復元"""
        if enabled:
            # 状態が記憶されている場合は元の状態を復元
            if self.ui_state_saved:
                for widget, was_enabled in self.ui_state.items():
                    widget.setEnabled(was_enabled)
                self.ui_state.clear()
                self.ui_state_saved = False
            else:
                # 状態が記憶されていない場合、self.copy_button以外を有効化
                for widget in self.findChildren(QWidget):
                    if widget != self.copy_button:
                        widget.setEnabled(True)
        else:
            # 初回は状態を記憶せず、2回目以降に状態を記憶
            if not self.ui_state:
                self.ui_state = {widget: widget.isEnabled() for widget in self.findChildren(QWidget)}
                self.ui_state_saved = True

            # UIを無効化
            for widget in self.findChildren(QWidget):
                widget.setEnabled(False)

    # フォルダ内の画像をロードする
    def load_images_from_folder(self, folder):
        #print(f"Current cache size: {self.cache_size}")
        self.status_bar.showMessage("Loading images...")
        self.clear_thumbnails()
        self.set_ui_enabled(False)  # UIを無効化
        
        if hasattr(self, 'image_loader'):
            self.image_loader.stop()
        
        self.image_loader = ImageLoader(folder, self.thumbnail_cache)
        self.image_loader.update_progress.connect(self.update_image_count)
        self.image_loader.update_thumbnail.connect(self.add_thumbnail)
        self.image_loader.finished_loading.connect(self.finalize_loading)
        self.image_loader.start()

    def update_image_count(self, loaded, total):
        selected_count = sum(1 for i in range(self.grid_layout.count()) if self.grid_layout.itemAt(i).widget().selected)
        if not self.copy_mode:
            self.status_bar.showMessage(f"Total images: {total}, Selected images: {selected_count}")
        else:
            self.status_bar.showMessage(f"Total images: {total}")

    def update_selected_count(self):
        selected_count = sum(1 for i in range(self.grid_layout.count()) if self.grid_layout.itemAt(i).widget().selected)
        total_images = self.grid_layout.count()
        self.status_bar.showMessage(f"Total images: {total_images}, Selected images: {selected_count}")

    # サムネイルを追加する
    def add_thumbnail(self, image_path, index):
        thumbnail = ImageThumbnail(image_path, self.thumbnail_cache, self.grid_widget)
        self.grid_layout.addWidget(thumbnail, index // self.thumbnail_columns, 
                                 index % self.thumbnail_columns)

    # 画像のロードが完了したときに呼び出されるスロット
    def finalize_loading(self, images):
        self.images = images
        # 新しい画像が読み込まれたときに現在の並べ替え順序を適用
        self.sort_images(self.current_sort)
        self.status_bar.showMessage(f"Total images: {len(self.images)}")
        self.set_ui_enabled(True)  # UIを有効化
        
        # 画像が0枚の場合、再読み込みボタンを表示
        if len(self.images) == 0:
            self.status_bar.showMessage("No images found. Please try again.")
            self.show_reload_button()
            return

    def show_reload_button(self):
        reload_button = QPushButton("Reload")
        reload_button.setStyleSheet("background-color: lightgray; font-size: 16px;")
        reload_button.clicked.connect(self.load_images)
        
        # 中央にボタンを配置
        for i in reversed(range(self.grid_layout.count())):
            self.grid_layout.itemAt(i).widget().setParent(None)
        self.grid_layout.addWidget(reload_button, 0, 0, Qt.AlignmentFlag.AlignCenter)

    def select_all(self):
        for i in range(self.grid_layout.count()):
            thumbnail = self.grid_layout.itemAt(i).widget()
            if not thumbnail.selected:
                thumbnail.selected = True
                if self.copy_mode:
                    thumbnail.order = len(self.selection_order) + 1
                    self.selection_order.append(thumbnail)
                    thumbnail.order_label.setText(str(thumbnail.order))
                    thumbnail.order_label.show()
                thumbnail.setStyleSheet("border: 3px solid orange;")
        self.update_selected_count()

    def unselect_all(self):
        for i in range(self.grid_layout.count()):
            thumbnail = self.grid_layout.itemAt(i).widget()
            thumbnail.selected = False
            thumbnail.setStyleSheet("")
            thumbnail.order = -1  # クリック順序をリセット
            thumbnail.order_label.hide()  # 番号ラベルを非表示にする
        self.selection_order = []
        self.update_selected_count()

    def check_and_remove_empty_folders(self, folder):
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
        folder = QFileDialog.getExistingDirectory(self, "Select Image Folder",self.current_folder)
        if folder:
            self.current_folder = folder  # 選択されたフォルダパスを保存
            # 選択したフォルダの親フォルダのパスを取得
            parent_folder = os.path.dirname(folder)
            
            # フォルダツリーのルートパスを親フォルダに設定
            self.folder_model.setRootPath(parent_folder)
            self.folder_view.setRootIndex(self.folder_model.index(parent_folder))

            # 選択したフォルダを展開して選択状態にする
            folder_index = self.folder_model.index(folder)
            self.folder_view.setCurrentIndex(folder_index)
            self.folder_view.expand(folder_index)

            # サブフォルダの空フォルダをチェック
            self.check_and_remove_empty_folders(folder)

            self.load_images_from_folder(folder)

    def filter_images(self):
        query = self.filter_box.text()
        if not query:
            self.clear_filter()
            return

        self.status_bar.showMessage("フィルタ中...")
        self.filter_button.setEnabled(False)
        self.filter_box.setEnabled(False)  # テキストボックスを無効化

        terms = query.split(',')
        matches = []

        for image_path in self.images:
            metadata = self.extract_metadata(image_path)
            if self.and_radio.isChecked():
                if all(term.lower() in metadata.lower() for term in terms):
                    matches.append(image_path)
            else:
                if any(term.lower() in metadata.lower() for term in terms):
                    matches.append(image_path)

        self.filter_results = matches  # フィルタ結果を保存
        self.clear_thumbnails()  # 既存のサムネイルをクリア

        for i, image_path in enumerate(matches):
            thumbnail = ImageThumbnail(image_path, self.thumbnail_cache, self.grid_widget)
            self.grid_layout.addWidget(thumbnail, i // self.thumbnail_columns, 
                                     i % self.thumbnail_columns)

        self.status_bar.clearMessage()
        self.filter_button.setEnabled(True)
        self.filter_box.setEnabled(True)  # テキストボックスを再度有効化

    def clear_filter(self):
        self.filter_results = []
        self.clear_thumbnails()
        for i, image_path in enumerate(self.images):
            thumbnail = ImageThumbnail(image_path, self.thumbnail_cache, self.grid_widget)
            self.grid_layout.addWidget(thumbnail, i // self.thumbnail_columns, 
                                     i % self.thumbnail_columns)

    def toggle_copy_mode(self):
        self.copy_mode = not self.copy_mode
        self.copy_mode_button.setText("Copy Mode Exit" if self.copy_mode else "Copy Mode")
        self.move_button.setEnabled(not self.copy_mode)
        self.copy_button.setEnabled(self.copy_mode)

        for i in range(self.grid_layout.count()):
            thumbnail = self.grid_layout.itemAt(i).widget()
            thumbnail.selected = False
            thumbnail.setStyleSheet("")
            thumbnail.order = -1  # クリック順序をリセット
            thumbnail.order_label.hide()  # 番号ラベルを非表示にする

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
            base_name, ext = os.path.splitext(os.path.basename(image_path))
            new_path = os.path.join(folder, base_name + ext)
            counter = 1

            # 同じ名前のファイルが存在するかどうかをチェックし、存在すればカウンターを追加
            while os.path.exists(new_path):
                new_path = os.path.join(folder, f"{base_name}_{counter}{ext}")
                counter += 1

            os.rename(image_path, new_path)
            if counter > 1:
                renamed_files.append(os.path.basename(new_path))

        self.unselect_all() # 選択状態を解除
        self.filter_box.clear()  # filter_boxの値をクリア
        self.clear_thumbnails()  # 現在のサムネイルをクリア

        self.image_loader = ImageLoader(self.image_loader.folder, self.thumbnail_cache) # 前回選択したフォルダでImageLoaderを再初期化
        self.image_loader.update_progress.connect(self.update_image_count)
        self.image_loader.update_thumbnail.connect(self.add_thumbnail)
        self.image_loader.finished_loading.connect(self.finalize_loading)
        self.image_loader.start()
        self.check_and_remove_empty_folders(self.image_loader.folder)  # サブフォルダの空フォルダをチェック

        if renamed_files:
            QMessageBox.information(self, "Renamed Files", "ファイル名が重複したためリネームしました:\n" + "\n".join(renamed_files))


    def copy_images(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
        if folder:
            # 既存のファイルをチェックして最終番号を取得
            existing_files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
            existing_numbers = []
            for f in existing_files:
                try:
                    num = int(f.split('_')[0])
                    existing_numbers.append(num)
                except ValueError:
                    continue

            next_number = max(existing_numbers, default=0) + 1

            # 選択された画像をコピー
            for thumbnail in self.selection_order:
                image_path = thumbnail.image_path
                base_name = os.path.basename(image_path)
                new_path = os.path.join(folder, f"{next_number:03}_{base_name}")

                # ファイルをコピー
                shutil.copy2(image_path, new_path)

                next_number += 1

            self.unselect_all()  # 選択状態を解除

    def extract_metadata(self, image_path):
        try:
            metadata = {}
            if image_path.lower().endswith('.png'):
                metadata = self._extract_png_metadata(image_path)
            else:
                metadata = self._extract_exif_metadata(image_path)
            return json.dumps(metadata, indent=4)
        except Exception as e:
            print(f"Error extracting metadata: {e}")
            return "Error extracting metadata"

    def _extract_png_metadata(self, image_path):
        image = QImage(image_path)
        raw_metadata = image.text()
        if raw_metadata:
            return self.parse_metadata(raw_metadata)
        return {"Comment": "No Metadata found in PNG text chunks."}

    def _extract_exif_metadata(self, image_path):
        img = Image.open(image_path)
        exif_data = img.info.get('exif')
        if exif_data:
            exif_dict = piexif.load(exif_data)
            user_comment = exif_dict['Exif'].get(piexif.ExifIFD.UserComment)
            if user_comment:
                comment = self.decode_unicode(user_comment)
                return self.parse_metadata(comment)
            return {"UserComment": "No UserComment found in EXIF data."}
        return {}

    def decode_unicode(self, array):
        try:
            return "".join(chr(b) for b in array if b != 0)
        except Exception as e:
            print(f"Error decoding unicode: {e}")
            return "Error decoding unicode"

    def parse_metadata(self, comment):
        metadata = {
            "positive": "",
            "negative": "",
            "others": ""
        }
        try:
            if comment.startswith("UNICODE"):
                comment = comment[7:]

            # "parameters:" を取り除く処理
            positive_part = comment.split("Negative prompt: ")[0]
            if "parameters: " in positive_part:
                positive_part = positive_part.replace("parameters: ", "").strip()

            metadata["positive"] = positive_part
            metadata["negative"] = comment.split("Negative prompt: ")[1].split("Steps: ")[0]
            metadata["others"] = "Steps: " + comment.split("Steps: ")[1]
        except IndexError:
            metadata["others"] = comment

        return metadata
    
    def restart_application(self):
        QApplication.quit()
        status = QProcess.startDetached(sys.executable, sys.argv)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())