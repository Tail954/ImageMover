import sys
import os
import json
import shutil
import piexif
from PIL import Image
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QRadioButton, QLineEdit, QTextEdit, QDialog,
    QScrollArea, QWidget, QGridLayout, QButtonGroup, QStatusBar, QMessageBox,
    QTreeView, QSplitter
)
from PyQt6.QtGui import QImage, QPixmap, QFileSystemModel
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QProcess, QDir

class ImageLoader(QThread):
    update_progress = pyqtSignal(int, int)  # 読み込み済み枚数と総枚数を送信

    def __init__(self, folder):
        super().__init__()
        self.folder = folder
        self.images = []
        self.total_files = 0

    def run(self):
        for root, _, files in os.walk(self.folder):
            self.total_files += len([file for file in files if file.lower().endswith(('.png', '.jpeg', '.jpg', '.webp'))])
        for root, _, files in os.walk(self.folder):
            for file in files:
                if file.lower().endswith(('.png', '.jpeg', '.jpg', '.webp')): 
                    self.images.append(os.path.join(root, file))
                    self.update_progress.emit(len(self.images), self.total_files)

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
            self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(new_pixmap)

class ImageThumbnail(QLabel):
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.selected = False
        self.order = -1  # クリック順序を保持するプロパティ
        self.setFixedSize(200, 200)
        self.setScaledContents(False)  # アスペクト比を維持するためにFalseに設定
        self.setPixmap(QPixmap(image_path).scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio))
        self.setToolTip(os.path.dirname(image_path))

        # 番号を表示するためのラベルを追加
        self.order_label = QLabel(self)
        self.order_label.setStyleSheet("color: white; background-color: black;")
        self.order_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.order_label.setGeometry(0, 0, 30, 30)
        self.order_label.hide()

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
        self.current_folder = ""  # 現在のフォルダパスを保持

        self.initUI()

    def initUI(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        layout = QVBoxLayout(self.central_widget)

        # スプリッターを作成して、フォルダツリーと画像表示部分を分割
        splitter = QSplitter(self)
        layout.addWidget(splitter)

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

        # Copy mode and UnSelect buttons
        button_layout = QHBoxLayout()
        self.select_all_button = QPushButton("Select All")
        self.select_all_button.clicked.connect(self.select_all)
        self.unselect_button = QPushButton("DeSelect All")
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
        splitter.addWidget(self.folder_view)
        splitter.addWidget(self.image_area_widget)
        splitter.setSizes([250, 800])  # 初期サイズを設定

        # Load images on startup
        self.load_images()
        
    def clear_thumbnails(self):
    #現在のサムネイルを全て削除する
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

    def on_folder_selected(self, index):
        folder_path = self.folder_model.filePath(index)
        self.load_images_from_folder(folder_path)

    def load_images_from_folder(self, folder):
        self.status_bar.showMessage("Loading images...")
        self.clear_thumbnails()  # サムネイルをクリア
        self.image_loader = ImageLoader(folder)
        self.image_loader.update_progress.connect(self.update_image_count)
        self.image_loader.finished.connect(self.display_thumbnails)
        self.image_loader.start()

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

    def load_images(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Image Folder")
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

            self.status_bar.showMessage("Loading images...")
            self.clear_thumbnails()
            self.image_loader = ImageLoader(folder)
            self.image_loader.update_progress.connect(self.update_image_count)
            self.image_loader.finished.connect(self.display_thumbnails)
            self.image_loader.start()

    def update_image_count(self, loaded, total):
        self.status_bar.showMessage(f"Loading images... {loaded}/{total} images loaded")

    def display_thumbnails(self):
        self.images = self.image_loader.images
        
        # 画像が0枚の場合、再読み込みボタンを表示
        if len(self.images) == 0:
            self.status_bar.showMessage("No images found. Please try again.")
            self.show_reload_button()
            return

        for i, image_path in enumerate(self.images):
            thumbnail = ImageThumbnail(image_path, self.grid_widget)
            self.grid_layout.addWidget(thumbnail, i // 5, i % 5)

        self.status_bar.showMessage(f"Total images: {len(self.images)}")

    def display_thumbnails(self):
        self.images = self.image_loader.images
        
        # 画像が0枚の場合、再読み込みボタンを表示
        if len(self.images) == 0:
            self.status_bar.showMessage("No images found. Please try again.")
            self.show_reload_button()
            return

        for i, image_path in enumerate(self.images):
            thumbnail = ImageThumbnail(image_path, self.grid_widget)
            self.grid_layout.addWidget(thumbnail, i // 5, i % 5)

        self.status_bar.showMessage(f"Total images: {len(self.images)}")

    def show_reload_button(self):
        reload_button = QPushButton("Reload")
        reload_button.setStyleSheet("background-color: lightgray; font-size: 16px;")
        reload_button.clicked.connect(self.load_images)
        
        # 中央にボタンを配置
        for i in reversed(range(self.grid_layout.count())):
            self.grid_layout.itemAt(i).widget().setParent(None)
        self.grid_layout.addWidget(reload_button, 0, 0, Qt.AlignmentFlag.AlignCenter)

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

        for i in reversed(range(self.grid_layout.count())):
            self.grid_layout.itemAt(i).widget().setParent(None)

        for i, image_path in enumerate(matches):
            thumbnail = ImageThumbnail(image_path, self.grid_widget)
            self.grid_layout.addWidget(thumbnail, i // 5, i % 5)

        self.status_bar.clearMessage()
        self.search_button.setEnabled(True)
        self.search_box.setEnabled(True)  # テキストボックスを再度有効化

    def clear_search(self):
        for i in reversed(range(self.grid_layout.count())):
            self.grid_layout.itemAt(i).widget().setParent(None)

        for i, image_path in enumerate(self.images):
            thumbnail = ImageThumbnail(image_path, self.grid_widget)
            self.grid_layout.addWidget(thumbnail, i // 5, i % 5)

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
            selected_images = [self.grid_layout.itemAt(i).widget().image_path for i in range(self.grid_layout.count()) if self.grid_layout.itemAt(i).widget().selected]
            for image_path in selected_images:
                new_path = os.path.join(folder, os.path.basename(image_path))
                os.rename(image_path, new_path)
            self.unselect_all()  # 選択状態を解除
            self.search_box.clear()  # search_boxの値をクリア
            self.clear_thumbnails()  # 現在のサムネイルをクリア
            self.image_loader = ImageLoader(self.image_loader.folder)  # 前回選択したフォルダでImageLoaderを再初期化
            self.image_loader.update_progress.connect(self.update_image_count)
            self.image_loader.finished.connect(self.display_thumbnails)
            self.image_loader.start()

    def copy_images(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
        if folder:
            for i, thumbnail in enumerate(self.selection_order, start=1):
                image_path = thumbnail.image_path
                new_path = os.path.join(folder, f"{i:03}_{os.path.basename(image_path)}")
                if os.path.exists(new_path):
                    overwrite = QMessageBox.question(self, "Overwrite", f"{new_path} already exists. Overwrite?", QMessageBox.Yes | QMessageBox.No)
                    if overwrite == QMessageBox.No:
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
