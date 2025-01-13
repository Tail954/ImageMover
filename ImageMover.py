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
    QTreeView, QSplitter
)
from PyQt6.QtGui import QImage, QPixmap, QFileSystemModel
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QProcess, QDir, QSize
from pathlib import Path
import concurrent.futures
import queue
import threading
from functools import lru_cache
import mimetypes

class ThumbnailCache:
    #サムネイルのキャッシュを管理するクラス
    def __init__(self, max_size=1000):
        self.cache = {}
        self.max_size = max_size
        self.lock = threading.Lock()

    @lru_cache(maxsize=1000)
    def get_thumbnail(self, image_path, size):
        #キャッシュからサムネイルを取得または生成
        with self.lock:
            if image_path in self.cache:
                return self.cache[image_path]
            
            try:
                image = QImage(image_path)
                pixmap = QPixmap.fromImage(image).scaled(
                    size, size, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                if len(self.cache) >= self.max_size:
                    self.cache.pop(next(iter(self.cache)))
                self.cache[image_path] = pixmap
                return pixmap
            except Exception as e:
                print(f"Error creating thumbnail for {image_path}: {e}")
                return None

class ImageLoader(QThread):
    #非同期で画像をロードするスレッド
    update_progress = pyqtSignal(int, int)
    update_thumbnail = pyqtSignal(str, int)
    finished_loading = pyqtSignal(list)

    def __init__(self, folder, thumbnail_size=200):
        super().__init__()
        self.folder = folder
        self.thumbnail_size = thumbnail_size
        self.images = []
        self.total_files = 0
        self._is_running = True
        self.thumbnail_cache = ThumbnailCache()
        self.valid_extensions = {'.png', '.jpeg', '.jpg', '.webp'}

    def stop(self):
        #スレッドを停止
        self._is_running = False

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

    def process_image(self, image_path):
        #個々の画像を処理
        try:
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
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Full Image")
        self.image_label = QLabel(self)
        self.pixmap = QPixmap(image_path)
        self.image_label.setPixmap(self.pixmap)
        layout = QVBoxLayout()
        layout.addWidget(self.image_label)
        self.setLayout(layout)
        self.setMinimumSize(200, 200)

    def resizeEvent(self, event):
        new_pixmap = self.pixmap.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(new_pixmap)

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
            self.setText("Error")

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
                dialog = ImageDialog(self.image_path, main_window)
                dialog.exec()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Move/Copy Application")
        self.setGeometry(100, 100, 1500, 800)
        self.images = []
        self.copy_mode = False
        self.selection_order = []  # クリック順序を保持するリスト
        self.current_folder = ""   # 現在のフォルダパスを保持
        self.search_results = []   # 検索結果を保持するリストを追加
        self.thumbnail_columns = 5  # サムネイルの列数を保持する変数を追加
        self.thumbnail_cache = ThumbnailCache()

        # 最後に選択したフォルダをロード
        self.load_last_values()
        self.initUI()

    def initUI(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        layout = QVBoxLayout(self.central_widget)

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

        # Search section
        search_layout = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search_images)
        self.search_box.returnPressed.connect(self.search_button.click)
        self.and_radio = QRadioButton("and")
        self.or_radio = QRadioButton("or")
        self.or_radio.setChecked(True)
        self.radio_group = QButtonGroup()
        self.radio_group.addButton(self.and_radio)
        self.radio_group.addButton(self.or_radio)
        search_layout.addWidget(self.search_box)
        search_layout.addWidget(self.and_radio)
        search_layout.addWidget(self.or_radio)
        search_layout.addWidget(self.search_button)
        image_layout.addLayout(search_layout)

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
                
        # 検索結果がある場合、それを再表示
        if self.search_results:
            self.clear_thumbnails()
            #現在のサムネイルを全て削除する
            for i, image_path in enumerate(self.search_results):
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

    # 最後に選択したフォルダをロードする
    def load_last_values(self):
        if os.path.exists("last_value.json"):
            with open("last_value.json", "r") as file:
                data = json.load(file)
                self.current_folder = data.get("folder", "")
                self.thumbnail_columns = data.get("thumbnail_columns", 5)

    # 最後に選択したフォルダを保存する
    def save_last_values(self):
        if not self.folder_view.isVisible():
            self.thumbnail_columns = self.thumbnail_columns - 1

        with open("last_value.json", "w") as file:
            json.dump({"folder": self.current_folder, "thumbnail_columns": self.thumbnail_columns}, file)

    def closeEvent(self, event):
        self.save_last_values()
        super().closeEvent(event)

    # フォルダが選択されたときに呼び出されるスロット
    def on_folder_selected(self, index):
        folder_path = self.folder_model.filePath(index)
        self.load_images_from_folder(folder_path)

    # フォルダ内の画像をロードする
    def load_images_from_folder(self, folder):
        self.status_bar.showMessage("Loading images...")
        self.clear_thumbnails()
        
        if hasattr(self, 'image_loader'):
            self.image_loader.stop()
            self.image_loader.wait()
        
        self.image_loader = ImageLoader(folder)
        self.image_loader.update_progress.connect(self.update_image_count)
        self.image_loader.update_thumbnail.connect(self.add_thumbnail)
        self.image_loader.finished_loading.connect(self.finalize_loading)
        self.image_loader.start()

    def update_image_count(self, loaded, total):
        self.status_bar.showMessage(f"Loading images... {loaded}/{total} images loaded")

    # サムネイルを追加する
    def add_thumbnail(self, image_path, index):
        thumbnail = ImageThumbnail(image_path, self.thumbnail_cache, self.grid_widget)
        self.grid_layout.addWidget(thumbnail, index // self.thumbnail_columns, 
                                 index % self.thumbnail_columns)

    # 画像のロードが完了したときに呼び出されるスロット
    def finalize_loading(self, images):
        self.images = images
        self.status_bar.showMessage(f"Total images: {len(self.images)}")
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

    def unselect_all(self):
        for i in range(self.grid_layout.count()):
            thumbnail = self.grid_layout.itemAt(i).widget()
            thumbnail.selected = False
            thumbnail.setStyleSheet("")
            thumbnail.order = -1  # クリック順序をリセット
            thumbnail.order_label.hide()  # 番号ラベルを非表示にする
        self.selection_order = []

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

    def search_images(self):
        query = self.search_box.text()
        if not query:
            self.clear_search()
            return

        self.status_bar.showMessage("検索中...")
        self.search_button.setEnabled(False)
        self.search_box.setEnabled(False)  # テキストボックスを無効化

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

        self.search_results = matches  # 検索結果を保存
        self.clear_thumbnails()  # 既存のサムネイルをクリア

        for i, image_path in enumerate(matches):
            thumbnail = ImageThumbnail(image_path, self.thumbnail_cache, self.grid_widget)
            self.grid_layout.addWidget(thumbnail, i // self.thumbnail_columns, 
                                     i % self.thumbnail_columns)

        self.status_bar.clearMessage()
        self.search_button.setEnabled(True)
        self.search_box.setEnabled(True)  # テキストボックスを再度有効化

    def clear_search(self):
        self.search_results = []
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
        if folder:
            selected_images = [self.grid_layout.itemAt(i).widget().image_path 
                             for i in range(self.grid_layout.count()) 
                             if self.grid_layout.itemAt(i).widget().selected]
            for image_path in selected_images:
                new_path = os.path.join(folder, os.path.basename(image_path))
                os.rename(image_path, new_path)
            self.unselect_all()  # 選択状態を解除
            self.search_box.clear()  # search_boxの値をクリア
            self.clear_thumbnails()  # 現在のサムネイルをクリア
            self.image_loader = ImageLoader(self.image_loader.folder)  # 前回選択したフォルダでImageLoaderを再初期化
            self.image_loader.update_progress.connect(self.update_image_count)
            self.image_loader.update_thumbnail.connect(self.add_thumbnail)
            self.image_loader.finished_loading.connect(self.finalize_loading)
            self.image_loader.start()
            self.check_and_remove_empty_folders(self.image_loader.folder)  # サブフォルダの空フォルダをチェック

    def copy_images(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
        if folder:
            for i, thumbnail in enumerate(self.selection_order, start=1):
                image_path = thumbnail.image_path
                new_path = os.path.join(folder, f"{i:03}_{os.path.basename(image_path)}")
                if os.path.exists(new_path):
                    overwrite = QMessageBox.question(self, "Overwrite", 
                                                   f"{new_path} already exists. Overwrite?",
                                                   QMessageBox.StandardButton.Yes | 
                                                   QMessageBox.StandardButton.No)
                    if overwrite == QMessageBox.StandardButton.No:
                        continue
                shutil.copy2(image_path, new_path)

    def extract_metadata(self, image_path):
        try:
            metadata = {}

            if image_path.lower().endswith('.png'):
                image = QImage(image_path)
                raw_metadata = image.text()
                if raw_metadata:
                    metadata.update(self.parse_metadata(raw_metadata))
                else:
                    metadata["Comment"] = "No Metadata found in PNG text chunks."
            else:
                img = Image.open(image_path)
                exif_data = img.info.get('exif')

                if exif_data:
                    exif_dict = piexif.load(exif_data)
                    user_comment = exif_dict['Exif'].get(piexif.ExifIFD.UserComment)

                    if user_comment:
                        comment = self.decode_unicode(user_comment)
                        metadata.update(self.parse_metadata(comment))
                    else:
                        metadata["UserComment"] = "No UserComment found in EXIF data."

            return json.dumps(metadata, indent=4)
        except Exception as e:
            print(f"Error extracting metadata: {e}")
            return "Error extracting metadata"

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