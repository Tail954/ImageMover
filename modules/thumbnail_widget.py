# modules/thumbnail_widget.py
import os
from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt
from modules.metadata import extract_metadata

class ImageThumbnail(QLabel):
    def __init__(self, image_path, thumbnail_cache, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.thumbnail_cache = thumbnail_cache
        self.selected = False
        self.order = -1
        self.setFixedSize(200, 200)
        self.setScaledContents(False)
        self.load_thumbnail()
        self.setToolTip(os.path.dirname(image_path))
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
            main_window = self.get_main_window()
            if main_window:
                if main_window.copy_mode:
                    if self.selected:
                        self.order = len(main_window.selection_order) + 1
                        main_window.selection_order.append(self)
                        self.order_label.setText(str(self.order))
                        self.order_label.show()
                    else:
                        try:
                            main_window.selection_order.remove(self)
                        except ValueError:
                            pass
                        self.order = -1
                        self.order_label.hide()
                        for i, thumb in enumerate(main_window.selection_order, start=1):
                            thumb.order = i
                            thumb.order_label.setText(str(i))
                else:
                    self.order = -1
                    self.order_label.hide()
                    main_window.update_selected_count()
            self.setStyleSheet("border: 3px solid orange;" if self.selected else "")
        elif event.button() == Qt.MouseButton.RightButton:
            main_window = self.get_main_window()
            if main_window:
                from modules.image_dialog import MetadataDialog
                metadata = extract_metadata(self.image_path)
                dialog = MetadataDialog(metadata, main_window)
                dialog.exec()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            main_window = self.get_main_window()
            if main_window:
                from modules.image_dialog import ImageDialog
                dialog = ImageDialog(self.image_path, main_window.preview_mode, main_window)
                dialog.exec()

    def get_main_window(self):
        main_window = self.parent()
        while main_window is not None and not hasattr(main_window, "update_selected_count"):
            main_window = main_window.parent()
        return main_window
