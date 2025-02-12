# modules/image_loader.py
import concurrent.futures
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal

class ImageLoader(QThread):
    update_progress = pyqtSignal(int, int)    # (loaded, total)
    update_thumbnail = pyqtSignal(str, int)   # (image_path, index)
    finished_loading = pyqtSignal(list)       # image paths list

    def __init__(self, folder, thumbnail_cache, thumbnail_size=200):
        super().__init__()
        self.folder = folder
        self.thumbnail_cache = thumbnail_cache
        self.thumbnail_size = thumbnail_size
        self.images = []
        self.total_files = 0
        self._is_running = True
        self.valid_extensions = {'.png', '.jpeg', '.jpg', '.webp'}

    def stop(self):
        self._is_running = False
        self.wait()

    def is_valid_image(self, file_path):
        return Path(file_path).suffix.lower() in self.valid_extensions

    def run(self):
        try:
            self.total_files = sum(1 for f in Path(self.folder).rglob('*')
                                   if self.is_valid_image(f))
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                future_to_path = {
                    executor.submit(self.process_image, str(f)): str(f)
                    for f in Path(self.folder).rglob('*') if self.is_valid_image(f)
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
        try:
            cache_key = f"{image_path}_{self.thumbnail_size}"
            if cache_key in self.thumbnail_cache.cache:
                return True
            self.thumbnail_cache.get_thumbnail(image_path, self.thumbnail_size)
            return True
        except Exception as e:
            print(f"Error processing image {image_path}: {e}")
            return False
