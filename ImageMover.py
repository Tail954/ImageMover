import os
import sys
import json
import piexif
from PIL import Image
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QRadioButton, QButtonGroup, QLabel, QFileDialog, QScrollArea, QGridLayout,
    QToolTip, QDialog, QTextEdit
)
from PyQt5.QtGui import QImage, QPixmap, QPainter
from PyQt5.QtCore import Qt, QEvent

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
            self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(new_pixmap)


class ImageMetadataPopup(QDialog):
    def __init__(self, metadata, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image Metadata")
        self.text_edit = QTextEdit(self)
        self.text_edit.setPlainText(metadata)
        layout = QVBoxLayout()
        layout.addWidget(self.text_edit)
        self.setLayout(layout)
        self.setMinimumSize(400, 300)


class ImageThumbnail(QLabel):
    def __init__(self, image_path, metadata, main_window):
        super().__init__()
        self.image_path = image_path
        self.metadata = metadata
        self.main_window = main_window
        self.setFixedSize(200, 200)
        self.setPixmap(QPixmap(image_path).scaled(self.size(), Qt.KeepAspectRatio))
        self.setFrameShape(QLabel.Box)
        self.setLineWidth(0)
        self.selected = False
        self.installEventFilter(self)
        QToolTip.setFont(self.font())

    def eventFilter(self, source, event):
        if event.type() == QEvent.Enter:
            QToolTip.showText(event.globalPos(), os.path.basename(self.image_path))
        return super().eventFilter(source, event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle_select()
        elif event.button() == Qt.RightButton:
            self.show_metadata_popup()
        elif event.type() == QEvent.MouseButtonDblClick:
            self.show_full_image()

    def toggle_select(self):
        if self.main_window.copy_mode_active:
            if not self.selected:
                self.main_window.selection_count += 1
                self.setText(str(self.main_window.selection_count).zfill(3))
            else:
                current_text = self.text()
                self.setText('')
                for thumb in self.main_window.thumbnails:
                    thumb_text = thumb.text()
                    if thumb.selected and thumb_text and int(thumb_text) > int(current_text):
                        thumb.setText(str(int(thumb_text) - 1).zfill(3))
                self.main_window.selection_count -= 1
            self.selected = not self.selected
            self.setStyleSheet("border: 3px solid orange;" if self.selected else "")
        else:
            self.selected = not self.selected
            self.setStyleSheet("border: 3px solid orange;" if self.selected else "")

    def show_metadata_popup(self):
        popup = ImageMetadataPopup(self.metadata, self)
        popup.exec_()

    def show_full_image(self):
        dialog = ImageDialog(self.image_path, self)
        dialog.exec_()


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Move/Copy Application")
        self.selection_count = 0
        self.copy_mode_active = False
        self.thumbnails = []
        self.init_ui()
        self.load_images()

    def init_ui(self):
        layout = QVBoxLayout()
        search_layout = QHBoxLayout()
        self.search_box = QLineEdit()
        self.and_radio = QRadioButton("and")
        self.or_radio = QRadioButton("or")
        self.or_radio.setChecked(True)
        self.radio_group = QButtonGroup()
        self.radio_group.addButton(self.and_radio)
        self.radio_group.addButton(self.or_radio)
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search_images)
        search_layout.addWidget(self.search_box)
        search_layout.addWidget(self.and_radio)
        search_layout.addWidget(self.or_radio)
        search_layout.addWidget(self.search_button)
        self.copy_mode_button = QPushButton("CopyMode")
        self.copy_mode_button.clicked.connect(self.toggle_copy_mode)
        layout.addLayout(search_layout)
        layout.addWidget(self.copy_mode_button)
        self.scroll_area = QScrollArea()
        self.scroll_widget = QWidget()
        self.grid_layout = QGridLayout()
        self.scroll_widget.setLayout(self.grid_layout)
        self.scroll_area.setWidget(self.scroll_widget)
        self.scroll_area.setWidgetResizable(True)
        layout.addWidget(self.scroll_area)
        button_layout = QHBoxLayout()
        self.move_button = QPushButton("Move")
        self.move_button.clicked.connect(self.move_images)
        self.copy_button = QPushButton("Copy")
        self.copy_button.clicked.connect(self.copy_images)
        self.copy_button.setDisabled(True)
        button_layout.addWidget(self.move_button)
        button_layout.addWidget(self.copy_button)
        layout.addLayout(button_layout)
        self.setLayout(layout)
        self.setGeometry(100, 100, 1150, 800)

    def load_images(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Source Folder")
        if not folder:
            sys.exit()
        self.image_paths = []
        for root, _, files in os.walk(folder):
            for file in files:
                if file.lower().endswith(('.png', '.jpeg', '.jpg', '.webp')):
                    self.image_paths.append(os.path.join(root, file))
        self.display_thumbnails()

    def display_thumbnails(self):
        self.thumbnails = []
        for i in reversed(range(self.grid_layout.count())):
            self.grid_layout.itemAt(i).widget().setParent(None)
        for index, image_path in enumerate(self.image_paths):
            metadata = self.extract_metadata(image_path)
            thumbnail = ImageThumbnail(image_path, metadata, self)
            self.thumbnails.append(thumbnail)
            self.grid_layout.addWidget(thumbnail, index // 5, index % 5)

    def extract_metadata(self, image_path):
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

    def toggle_copy_mode(self):
        self.copy_mode_active = not self.copy_mode_active
        self.copy_mode_button.setText("CopyMode Exit" if self.copy_mode_active else "CopyMode")
        self.move_button.setDisabled(self.copy_mode_active)
        self.copy_button.setEnabled(self.copy_mode_active)
        self.selection_count = 0
        for thumb in self.thumbnails:
            thumb.selected = False
            thumb.setText('')
            thumb.setStyleSheet("")

    def search_images(self):
        query = self.search_box.text().strip()
        if not query:
            self.display_thumbnails()
            return
        keywords = query.split(',')
        filtered_images = []
        for image_path in self.image_paths:
            metadata = self.extract_metadata(image_path)
            match = all(keyword.lower() in metadata.lower() for keyword in keywords) if self.and_radio.isChecked() else \
                    any(keyword.lower() in metadata.lower() for keyword in keywords)
            if match:
                filtered_images.append(image_path)
        self.image_paths = filtered_images
        self.display_thumbnails()

    def move_images(self):
        destination = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
        if not destination:
            return
        for thumb in self.thumbnails:
            if thumb.selected:
                os.rename(thumb.image_path, os.path.join(destination, os.path.basename(thumb.image_path)))
        self.load_images()

    def copy_images(self):
        destination = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
        if not destination:
            return
        for thumb in self.thumbnails:
            if thumb.selected:
                new_name = f"{thumb.text()}{os.path.splitext(thumb.image_path)[1]}"
                new_path = os.path.join(destination, new_name)
                Image.open(thumb.image_path).save(new_path)
        self.load_images()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())
