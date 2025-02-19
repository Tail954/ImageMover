# modules/image_dialog.py
import json
import os
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
        self.image_path = image_path
        self.parent_window = parent
        
        # Get the list of all images from parent (main window)
        self.all_images = self.get_all_images()
        self.current_index = self.all_images.index(image_path) if image_path in self.all_images else 0
        
        self.layout = QVBoxLayout()
        
        # Create navigation and tool layout
        self.tool_layout = QHBoxLayout()
        
        # Add navigation buttons
        self.prev_button = QPushButton("← Previous")
        self.prev_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.prev_button.clicked.connect(self.show_previous_image)
        self.prev_button.setEnabled(self.current_index > 0)
        
        self.next_button = QPushButton("Next →")
        self.next_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.next_button.clicked.connect(self.show_next_image)
        self.next_button.setEnabled(self.current_index < len(self.all_images) - 1)
        
        # Add counter label
        self.counter_label = QLabel(f"{self.current_index + 1} / {len(self.all_images)}")
        self.counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.tool_layout.addWidget(self.prev_button)
        self.tool_layout.addWidget(self.counter_label)
        self.tool_layout.addWidget(self.next_button)
        self.tool_layout.addStretch()
        
        # Maximize button
        self.maximize_button = QPushButton("□")
        self.maximize_button.setFixedSize(30, 30)
        self.maximize_button.clicked.connect(self.toggle_maximize)
        self.tool_layout.addWidget(self.maximize_button)
        
        self.layout.addLayout(self.tool_layout)
        
        # Setup image display based on preview mode
        if self.preview_mode == 'seamless':
            self.setup_seamless_mode(image_path)
        else:
            self.setup_wheel_mode(image_path)
            
        self.setLayout(self.layout)
        self.setMinimumSize(600, 500)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def get_all_images(self):
        """Get all image paths from the main window"""
        if not self.parent_window:
            return [self.image_path]
            
        # Get the current list of images (filtered or all)
        if hasattr(self.parent_window, 'filter_results') and self.parent_window.filter_results:
            return self.parent_window.filter_results
        elif hasattr(self.parent_window, 'images'):
            return self.parent_window.images
        else:
            return [self.image_path]

    def show_next_image(self):
        """Navigate to the next image in the list"""
        if self.current_index < len(self.all_images) - 1:
            self.current_index += 1
            self.load_image(self.all_images[self.current_index])
            self.update_navigation_buttons()

    def show_previous_image(self):
        """Navigate to the previous image in the list"""
        if self.current_index > 0:
            self.current_index -= 1
            self.load_image(self.all_images[self.current_index])
            self.update_navigation_buttons()

    def load_image(self, image_path):
        """Load and display the new image"""
        self.image_path = image_path
        self.pixmap = QPixmap(image_path)
        self.setWindowTitle(f"Full Image - {os.path.basename(image_path)}")
        
        if self.preview_mode == 'seamless':
            # Resize to fit the current window
            scaled_pixmap = self.pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.image_label.setPixmap(scaled_pixmap)
        else:
            # Reset zoom factor and display original image
            self.scale_factor = 1.0
            self.image_label.setPixmap(self.pixmap)

    def update_navigation_buttons(self):
        """Update button states and counter"""
        self.prev_button.setEnabled(self.current_index > 0)
        self.next_button.setEnabled(self.current_index < len(self.all_images) - 1)
        self.counter_label.setText(f"{self.current_index + 1} / {len(self.all_images)}")

    def setup_seamless_mode(self, image_path):
        self.image_label = QLabel(self)
        self.pixmap = QPixmap(image_path)
        scaled_pixmap = self.pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.image_label.setPixmap(scaled_pixmap)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.image_label)

    def setup_wheel_mode(self, image_path):
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.image_label = QLabel()
        self.pixmap = QPixmap(image_path)
        self.image_label.setPixmap(self.pixmap)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidget(self.image_label)
        self.scroll_area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.layout.addWidget(self.scroll_area)
        self.setToolTip("Ctrl + Wheel to zoom, drag to scroll")
        self.resize(1000, 900)

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

    def keyPressEvent(self, event):
        """Handle keyboard navigation"""
        if event.key() == Qt.Key.Key_Right or event.key() == Qt.Key.Key_Space:
            self.show_next_image()
        elif event.key() == Qt.Key.Key_Left or event.key() == Qt.Key.Key_Backspace:
            self.show_previous_image()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

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