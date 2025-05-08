# \modules\thumbnail_cache.py
# 画像のサムネイルをメモリ上にキャッシュし、高速な表示をサポートするクラス。
import threading
import logging # logging をインポート
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import Qt

logger = logging.getLogger(__name__) # ロガーを取得

# ImageThumbnail で使われているデフォルトサイズに合わせておく
DEFAULT_THUMBNAIL_SIZE = 200

class ThumbnailCache:
    def __init__(self, max_size=1000):
        self.cache = {}
        self.max_size = max_size
        self.lock = threading.Lock()

    def get_thumbnail(self, image_path, size):
        """指定されたサイズのサムネイルをキャッシュから取得、なければ生成してキャッシュ"""
        cache_key = f"{image_path}_{size}"
        with self.lock:
            if cache_key in self.cache:
                # logger.debug(f"Cache hit for: {cache_key}")
                return self.cache[cache_key]

        # logger.debug(f"Cache miss for: {cache_key}, generating...")
        try:
            image = QImage(image_path)
            if image.isNull():
                logger.error(f"Failed to load image {image_path}")
                return None
            pixmap = QPixmap.fromImage(image).scaled(
                size, size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            with self.lock:
                # キャッシュサイズ管理
                if len(self.cache) >= self.max_size:
                    # 最も古いキーを削除 (Python 3.7+ では挿入順が保証される)
                    try:
                        oldest_key = next(iter(self.cache))
                        del self.cache[oldest_key]
                        # logger.debug(f"Cache full, removed oldest: {oldest_key}")
                    except StopIteration:
                        pass # キャッシュが空の場合は何もしない
                self.cache[cache_key] = pixmap
            return pixmap
        except Exception as e:
            logger.error(f"Error creating thumbnail for {image_path}: {e}")
            return None

    def remove(self, image_path, size=None):
        """
        指定された画像のサムネイルをキャッシュから削除する。
        size が指定されない場合は、デフォルトのサムネイルサイズを使用する。
        """
        # size が None の場合はデフォルト値を使用
        effective_size = size if size is not None else DEFAULT_THUMBNAIL_SIZE
        cache_key = f"{image_path}_{effective_size}"
        with self.lock:
            if cache_key in self.cache:
                try:
                    del self.cache[cache_key]
                    # logger.debug(f"Removed from cache: {cache_key}")
                except KeyError:
                    # ほぼ起こらないはずだが念のため
                    logger.warning(f"KeyError during remove: {cache_key}")
            # else:
                # logger.debug(f"Key not found in cache for removal: {cache_key}")

    def clear(self):
        """キャッシュをすべてクリアする"""
        with self.lock:
            self.cache.clear()
            # logger.debug("Cache cleared.")

    def resize(self, new_max_size):
        """キャッシュの最大サイズを変更し、必要なら古いエントリを削除する"""
        with self.lock:
            self.max_size = new_max_size
            # logger.debug(f"Cache max size resized to: {new_max_size}")
            # サイズオーバーしている分を削除
            while len(self.cache) > self.max_size:
                try:
                    oldest_key = next(iter(self.cache))
                    del self.cache[oldest_key]
                    # logger.debug(f"Cache resized, removed oldest: {oldest_key}")
                except StopIteration:
                    break # キャッシュが空になったらループ終了
