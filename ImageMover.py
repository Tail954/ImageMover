import sys
import os
import shutil
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QPushButton,
    QLineEdit, QFileDialog, QLabel, QScrollArea, QWidget, QGridLayout,
    QCheckBox, QTextEdit, QDialog
)
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import Qt, QTimer, QEvent
from PIL import Image
import piexif
import json


class ImageMoverApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Image Mover')
        self.setGeometry(100, 100, 800, 800)
        self.folder_path = ''
        self.image_widgets = []
        self.image_data = []

        self.initUI()
        self.showFolderDialog()

    def initUI(self):
        self.main_widget = QWidget()
        self.main_layout = QVBoxLayout()

        self.initSearchLayout()
        self.initScrollArea()
        self.initMoveButton()
        self.initStatusBar()

        self.main_widget.setLayout(self.main_layout)
        self.setCentralWidget(self.main_widget)

    def initSearchLayout(self):
        self.search_layout = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_button = QPushButton('Search')
        self.search_button.clicked.connect(self.searchImages)
        self.search_bar.installEventFilter(self)
        self.search_layout.addWidget(self.search_bar)
        self.search_layout.addWidget(self.search_button)
        self.main_layout.addLayout(self.search_layout)

    def initScrollArea(self):
        self.scroll_area = QScrollArea()
        self.scroll_widget = QWidget()
        self.grid_layout = QGridLayout()
        self.scroll_widget.setLayout(self.grid_layout)
        self.scroll_area.setWidget(self.scroll_widget)
        self.scroll_area.setWidgetResizable(True)
        self.main_layout.addWidget(self.scroll_area)

    def initMoveButton(self):
        self.move_button = QPushButton('Move')
        self.move_button.clicked.connect(self.moveImages)
        self.main_layout.addWidget(self.move_button)

    def initStatusBar(self):
        self.status_bar = QLabel('')
        self.main_layout.addWidget(self.status_bar)

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.KeyPress and source == self.search_bar:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.searchImages()
                return True
        return super().eventFilter(source, event)

    def showFolderDialog(self):
        folder = QFileDialog.getExistingDirectory(self, 'Select Folder')
        if folder:
            self.folder_path = folder
            self.loadImages()

    def loadImages(self):
        self.image_data.clear()
        self.clearGridLayout(self.grid_layout)

        self.image_widgets.clear()

        supported_formats = ['.png', '.jpeg', '.jpg', '.webp']
        count = 0
        for root, dirs, files in os.walk(self.folder_path):
            for file in files:
                if any(file.lower().endswith(ext) for ext in supported_formats):
                    file_path = os.path.join(root, file)
                    metadata = self.extractMetadata(file_path)
                    self.image_data.append({'path': file_path, 'metadata': metadata, 'selected': False, 'folder': root})
                    count += 1

        self.status_bar.setText(f'Loading {count} images...')
        QTimer.singleShot(100, self.displayImages)

    def clearGridLayout(self, layout):
        for i in reversed(range(layout.count())):
            widget_to_remove = layout.itemAt(i).widget()
            layout.removeWidget(widget_to_remove)
            widget_to_remove.setParent(None)

    def extractMetadata(self, image_path):
        try:
            if image_path.lower().endswith('.png'):
                image = QImage(image_path)
                metadata = image.text()
                return metadata if metadata else "No Metadata"
            else:
                img = Image.open(image_path)
                exif_data = img.info.get('exif')

                metadata = {}

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
            metadata["positive"] = comment.split("Negative prompt: ")[0]
            metadata["negative"] = comment.split("Negative prompt: ")[1].split("Steps: ")[0]
            metadata["others"] = "Steps: " + comment.split("Steps: ")[1]
        except IndexError:
            metadata["others"] = comment

        return metadata

    def displayImages(self):
        row, col = 0, 0
        for i, data in enumerate(self.image_data):
            image_label = QLabel()
            image = QImage(data['path'])
            pixmap = QPixmap.fromImage(image.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio))
            image_label.setPixmap(pixmap)
            image_label.setToolTip(data['folder'])
            image_label.mousePressEvent = lambda event, idx=i: self.handleMousePress(event, idx)
            image_label.mouseDoubleClickEvent = lambda event, idx=i: self.showFullImage(event, idx)
            check_box = QCheckBox()
            self.grid_layout.addWidget(image_label, row, col)
            self.grid_layout.addWidget(check_box, row, col)
            self.image_widgets.append({'label': image_label, 'checkbox': check_box})
            if col == 4:
                col = 0
                row += 1
            else:
                col += 1
        self.status_bar.setText('Images loaded')

        num_columns = 5
        image_width = 200
        spacing = 30
        extra_margin = 50

        window_width = num_columns * (image_width + spacing) + extra_margin
        self.resize(window_width, self.height())

    def handleMousePress(self, event, idx):
        if event.button() == Qt.MouseButton.LeftButton:
            self.image_widgets[idx]['checkbox'].setChecked(not self.image_widgets[idx]['checkbox'].isChecked())
        elif event.button() == Qt.MouseButton.RightButton:
            self.showMetadata(self.image_data[idx]['metadata'])

    def showMetadata(self, metadata):
        metadata_dialog = QDialog()
        metadata_dialog.setWindowTitle("Image Metadata")
        metadata_dialog.setGeometry(100, 100, 400, 300)
        layout = QVBoxLayout()
        metadata_text = QTextEdit()
        metadata_text.setReadOnly(True)
        metadata_text.setText(metadata)
        layout.addWidget(metadata_text)
        metadata_dialog.setLayout(layout)
        metadata_dialog.exec()

    def searchImages(self):
        query = self.search_bar.text().lower()
        for i, data in enumerate(self.image_data):
            metadata_str = data['metadata'] if isinstance(data['metadata'], str) else json.dumps(data['metadata'])
            if query in metadata_str.lower():
                self.image_widgets[i]['label'].show()
                self.image_widgets[i]['checkbox'].show()
            else:
                self.image_widgets[i]['label'].hide()
                self.image_widgets[i]['checkbox'].hide()

    def moveImages(self):
        dest_folder = QFileDialog.getExistingDirectory(self, 'Select Destination Folder')
        if dest_folder:
            for i, data in enumerate(self.image_data):
                if self.image_widgets[i]['checkbox'].isChecked():
                    shutil.move(data['path'], dest_folder)
            self.loadImages()

    def showFullImage(self, event, idx):
        if event.button() == Qt.MouseButton.LeftButton:
            image_path = self.image_data[idx]['path']
            image_dialog = ImageDialog(image_path, self)
            image_dialog.exec()


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


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = ImageMoverApp()
    ex.show()
    sys.exit(app.exec())
