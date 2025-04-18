# modules/thumbnail_cache.py
import threading
import logging
from collections import OrderedDict
from typing import Optional, Dict
from PyQt6.QtGui import QImage, QPixmap, QImageReader
from PyQt6.QtCore import Qt, QSize
# from .constants import DEFAULT_THUMBNAIL_SIZE # 必要に応じてデフォルトサイズを使用

logger = logging.getLogger(__name__)

class ThumbnailCache:
    """
    画像サムネイル (QPixmap) をメモリ内にキャッシュするクラス。
    スレッドセーフであり、キャッシュサイズの上限を持ちます (FIFO)。
    """
    def __init__(self, max_size: int = 1000):
        """
        ThumbnailCacheを初期化します。

        Args:
            max_size: キャッシュできるサムネイルの最大数。
        """
        if max_size <= 0:
            logger.warning(f"キャッシュサイズには正の整数を指定してください。デフォルト値 1000 を使用します。 Got: {max_size}")
            max_size = 1000
        # OrderedDict を使用して FIFO (First-In, First-Out) を簡単に実装
        self._cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._max_size: int = max_size
        self._lock: threading.Lock = threading.Lock()
        logger.info(f"サムネイルキャッシュを初期化しました。最大サイズ: {self._max_size}")

    def get_thumbnail(self, image_path: str, size: int) -> Optional[QPixmap]:
        """
        指定された画像パスとサイズのサムネイルを取得します。
        キャッシュに存在すればそれを返し、なければ生成してキャッシュに追加します。

        Args:
            image_path: サムネイルを取得する画像のパス。
            size: サムネイルの目標サイズ (幅・高さ)。

        Returns:
            生成されたQPixmapオブジェクト、またはエラー時はNone。
        """
        if not image_path or size <= 0:
            logger.warning(f"無効な引数で get_thumbnail が呼び出されました: path='{image_path}', size={size}")
            return None

        cache_key = f"{image_path}_{size}"

        # まずロックなしでキャッシュをチェック (高速化のため)
        # Note: スレッドセーフではないが、ヒットした場合のロック取得を回避できる
        #       もしヒットせず、その間に他のスレッドが生成した場合、二重生成の可能性はあるが、
        #       最終的にロック内で再チェックするので問題ない。
        if cache_key in self._cache:
             with self._lock:
                 # ロック取得後、再度チェックしてキャッシュから取得（他のスレッドが削除した可能性）
                 if cache_key in self._cache:
                     # LRU の場合: self._cache.move_to_end(cache_key)
                     return self._cache[cache_key]

        # キャッシュにない場合、生成する
        try:
            # QImageReader を使用して効率的に読み込み、必要に応じてサイズ制限
            reader = QImageReader(image_path)
            if not reader.canRead():
                 logger.warning(f"画像ファイルを読み込めません (QImageReader): {image_path}")
                 return None

            # 必要であればここで画像の最大サイズ制限などをかけられる
            # reader.setScaledSize(QSize(max_w, max_h))

            # QImage を読み込み
            image: QImage = reader.read()
            if image.isNull():
                logger.warning(f"空のQImageが読み込まれました: {image_path}, Error: {reader.errorString()}")
                return None

            # QPixmapに変換してスケーリング
            pixmap = QPixmap.fromImage(image).scaled(
                size, size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

            # キャッシュに追加（ロック内で）
            with self._lock:
                # キャッシュサイズ制限を確認し、必要であれば古いものを削除 (FIFO)
                if len(self._cache) >= self._max_size:
                    # OrderedDict なので popitem(last=False) で最初の要素 (最も古い) を削除
                    removed_key, _ = self._cache.popitem(last=False)
                    logger.debug(f"キャッシュサイズ上限のため削除: {removed_key}")

                # キャッシュに追加
                self._cache[cache_key] = pixmap
                # LRU の場合: self._cache.move_to_end(cache_key) # 追加時も最後に移動

            logger.debug(f"サムネイルを生成・キャッシュしました: {cache_key}")
            return pixmap

        except Exception as e:
            # PIL.UnidentifiedImageError やその他の予期せぬエラー
            logger.error(f"サムネイル生成中にエラーが発生しました ({image_path}): {e}", exc_info=False) # exc_info=False でスタックトレース抑制も可
            return None

    def clear(self) -> None:
        """キャッシュを完全にクリアします。"""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
        logger.info(f"サムネイルキャッシュをクリアしました。削除されたアイテム数: {count}")

    def resize(self, new_max_size: int) -> None:
        """
        キャッシュの最大サイズを変更します。
        新しいサイズが現在のキャッシュ数より小さい場合、古いエントリが削除されます。

        Args:
            new_max_size: 新しい最大キャッシュサイズ。
        """
        if new_max_size <= 0:
            logger.warning(f"無効なキャッシュサイズが指定されました: {new_max_size}。変更は行われません。")
            return

        with self._lock:
            old_max_size = self._max_size
            self._max_size = new_max_size
            removed_count = 0
            # 新しいサイズに合わせて古いエントリを削除
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False) # FIFO
                removed_count += 1
        logger.info(f"キャッシュ最大サイズが {old_max_size} から {self._max_size} に変更されました。")
        if removed_count > 0:
             logger.info(f"{removed_count} 個の古いキャッシュエントリが削除されました。")

    @property
    def current_size(self) -> int:
        """現在のキャッシュサイズ（アイテム数）を返します。"""
        with self._lock:
            return len(self._cache)

    @property
    def max_size(self) -> int:
        """設定されている最大キャッシュサイズを返します。"""
        return self._max_size