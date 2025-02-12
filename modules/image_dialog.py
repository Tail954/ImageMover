# modules/image_dialog.py
import json
from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QScrollArea, QWidget, QApplication, QTextEdit
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

class MetadataDialog(QDialog):
    def __init__(self, metadata, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Metadata")
        metadata_dict = json.loads(metadata)
        self.positive_edit = QTextEdit(self)
        self.negative_edit = QTextEdit(self)
        self.others_edit = QTextEdit(self)
        self.positive_edit.setPlainText(metadata_dict.get("positive_prompt", "No positive metadata"))
        self.negative_edit.setPlainText(metadata_dict.get("negative_prompt", "No negative metadata"))
        self.others_edit.setPlainText(metadata_dict.get("generation_info", "No generation info"))
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
        self.saved_geometry = None
        self.layout = QVBoxLayout()
        self.tool_layout = QHBoxLayout()
        self.tool_layout.addStretch()
        self.maximize_button = QPushButton("□")
        self.maximize_button.setFixedSize(30, 30)
        self.maximize_button.clicked.connect(self.toggle_maximize)
        self.tool_layout.addWidget(self.maximize_button)
        self.layout.addLayout(self.tool_layout)
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
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.image_label = QLabel()
        self.pixmap = QPixmap(image_path)
        self.image_label.setPixmap(self.pixmap)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidget(self.image_label)
        self.layout.addWidget(self.scroll_area)
        self.setToolTip("Ctrl + Wheel to zoom, drag to scroll")
        self.resize(1000,900)

    def wheelEvent(self, event):
        if self.preview_mode == 'wheel':
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                delta = event.angleDelta().y()
                if delta > 0:
                    self.scale_factor *= 1.1
                else:
                    self.scale_factor *= 0.9
                scaled_pixmap = self.pixmap.scaled(
                    self.pixmap.size() * self.scale_factor,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.image_label.setPixmap(scaled_pixmap)
            else:
                self.scroll_area.verticalScrollBar().setValue(
                    self.scroll_area.verticalScrollBar().value() - event.angleDelta().y()
                )

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
                self.saved_geometry = None
