# modules/thumbnail_cache.py
import threading
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import Qt

class ThumbnailCache:
    def __init__(self, max_size=1000):
        self.cache = {}
        self.max_size = max_size
        self.lock = threading.Lock()

    def get_thumbnail(self, image_path, size):
        cache_key = f"{image_path}_{size}"
        with self.lock:
            if cache_key in self.cache:
                return self.cache[cache_key]
        try:
            image = QImage(image_path)
            pixmap = QPixmap.fromImage(image).scaled(
                size, size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
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
        with self.lock:
            self.cache.clear()

    def resize(self, new_max_size):
        with self.lock:
            self.max_size = new_max_size
            while len(self.cache) > self.max_size:
                self.cache.pop(next(iter(self.cache)))
