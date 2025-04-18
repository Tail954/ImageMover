# modules/image_loader.py
import concurrent.futures
import logging
from pathlib import Path
from typing import List, Optional
from PyQt6.QtCore import QThread, pyqtSignal, QObject
from .thumbnail_cache import ThumbnailCache
from .constants import VALID_IMAGE_EXTENSIONS, IMAGE_LOADER_MAX_WORKERS, DEFAULT_THUMBNAIL_SIZE

logger = logging.getLogger(__name__)

class ImageLoader(QThread):
    """
    指定されたフォルダ内の画像ファイルを非同期的に検索し、
    サムネイルを生成（またはキャッシュから取得）するワーカースレッド。
    """
    # --- シグナル定義 ---
    # (loaded_count, total_count)
    update_progress = pyqtSignal(int, int)
    # (image_path_str, index) - PyQtはPathオブジェクトを直接シグナルで扱えない場合があるためstr
    update_thumbnail = pyqtSignal(str, int)
    # (image_paths_list_str)
    finished_loading = pyqtSignal(list)
    # エラーメッセージ通知用シグナル (オプション)
    error_occurred = pyqtSignal(str)

    def __init__(self, folder: str,
                 thumbnail_cache: ThumbnailCache,
                 thumbnail_size: int = DEFAULT_THUMBNAIL_SIZE,
                 parent: Optional[QObject] = None):
        """
        ImageLoaderを初期化します。

        Args:
            folder: 画像を検索するフォルダのパス。
            thumbnail_cache: 使用するThumbnailCacheのインスタンス。
            thumbnail_size: 生成するサムネイルのサイズ。
            parent: 親QObject。
        """
        super().__init__(parent)
        self.folder: Path = Path(folder)
        self.thumbnail_cache: ThumbnailCache = thumbnail_cache
        self.thumbnail_size: int = thumbnail_size
        self.images: List[str] = []
        self._is_running: bool = True
        self._executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
        logger.info(f"ImageLoader initialized for folder: {self.folder}")

    def stop(self) -> None:
        """画像読み込み処理を停止します。"""
        logger.info("ImageLoader の停止リクエストを受け取りました。")
        self._is_running = False
        if self._executor:
            # 実行中のタスクをキャンセルしようとし、完了を待たずにシャットダウン
            # cancel_futures=True は Python 3.9+
            try:
                 self._executor.shutdown(wait=False, cancel_futures=True)
            except TypeError: # Python 3.8 以前には cancel_futures がない
                 self._executor.shutdown(wait=False)
            logger.info("ThreadPoolExecutor をシャットダウンしました。")
        # QThread.wait() はスレッドが終了するのを待つ
        if self.isRunning():
             logger.debug("ワーカースレッドの終了を待機します...")
             self.wait() # run() メソッドの完了を待つ
             logger.info("ワーカースレッドが正常に終了しました。")

    def _is_valid_image(self, file_path: Path) -> bool:
        """ファイルパスが有効な画像ファイル拡張子を持っているか確認します。"""
        return file_path.is_file() and file_path.suffix.lower() in VALID_IMAGE_EXTENSIONS

    def run(self) -> None:
        """
        ワーカースレッドのメイン処理。
        フォルダをスキャンし、画像を処理してシグナルを発行します。
        """
        logger.info(f"画像読み込みスレッドを開始します: {self.folder}")
        self._is_running = True
        self.images = []
        processed_count = 0

        try:
            # フォルダが存在しない場合
            if not self.folder.is_dir():
                 error_msg = f"指定されたフォルダが見つかりません: {self.folder}"
                 logger.error(error_msg)
                 self.error_occurred.emit(error_msg)
                 self.finished_loading.emit([]) # 空のリストで終了を通知
                 return

            # 有効な画像ファイルのリストを取得
            logger.debug(f"フォルダ '{self.folder}' 内の画像ファイルを検索中...")
            image_files = [p for p in self.folder.rglob('*') if self._is_valid_image(p)]
            total_files = len(image_files)
            logger.info(f"{total_files} 個の画像ファイルが見つかりました。")
            self.update_progress.emit(0, total_files) # 初期進捗

            if total_files == 0:
                 logger.info("画像ファイルが見つからなかったため、処理を終了します。")
                 self.finished_loading.emit([])
                 return

            # スレッドプールで画像を処理
            self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=IMAGE_LOADER_MAX_WORKERS)
            future_to_path = {
                self._executor.submit(self._process_image, path): path
                for path in image_files
            }

            for future in concurrent.futures.as_completed(future_to_path):
                if not self._is_running:
                    logger.info("処理が中断されました。")
                    break # ループを抜ける

                path = future_to_path[future]
                try:
                    success = future.result() # _process_image の結果 (True/False)
                    if success:
                        # 成功した場合のみリストに追加し、サムネイル更新シグナルを発行
                        # PyQtのシグナルにはstr型で渡すのが安全
                        image_path_str = str(path)
                        self.images.append(image_path_str)
                        # インデックスは processed_count を使う
                        self.update_thumbnail.emit(image_path_str, processed_count)
                    # success が False の場合 (処理失敗) はリストに追加しない
                    # エラーログは _process_image 内で出力される

                except Exception as e:
                    # future.result() で例外が発生した場合 (通常は _process_image 内で捕捉されるはずだが念のため)
                    logger.error(f"画像処理フューチャの結果取得中にエラーが発生しました ({path}): {e}", exc_info=True)
                finally:
                     processed_count += 1
                     # 常に進捗は更新する
                     self.update_progress.emit(processed_count, total_files)

            # executor をクリーンアップ
            self._executor.shutdown(wait=True) # すべてのタスク完了を待つ (中断されていなければ)
            self._executor = None

            # 最終的な結果を通知
            if self._is_running:
                 logger.info(f"画像読み込みが完了しました。ロードされた画像数: {len(self.images)}")
                 self.finished_loading.emit(self.images)
            else:
                 logger.info("画像読み込みが中断されたため、完了シグナルは発行しません。")
                 # 中断された場合でも、空リストで終了通知が必要ならここで行う
                 # self.finished_loading.emit([])

        except Exception as e:
            # run メソッド全体での予期せぬエラー
            error_msg = f"ImageLoader スレッドで予期せぬエラーが発生しました: {e}"
            logger.critical(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            if self._executor: # エラー発生時も executor を閉じる試み
                 self._executor.shutdown(wait=False)
                 self._executor = None
            # エラー発生時も finished_loading を発行してメインスレッドの待機を解除するべきか検討
            # self.finished_loading.emit([])

        finally:
            logger.info("画像読み込みスレッドが終了します。")


    def _process_image(self, image_path: Path) -> bool:
        """
        個々の画像を処理し、サムネイルキャッシュに追加（または取得）します。
        ThreadPoolExecutor によって呼び出されます。

        Args:
            image_path: 処理する画像のPathオブジェクト。

        Returns:
            処理に成功した場合はTrue、失敗した場合はFalse。
        """
        if not self._is_running:
             return False # 処理中に停止リクエストがあった場合

        try:
            # ThumbnailCache を使用してサムネイルを取得（または生成）
            pixmap = self.thumbnail_cache.get_thumbnail(str(image_path), self.thumbnail_size)
            if pixmap:
                # logger.debug(f"サムネイル処理成功: {image_path}")
                return True
            else:
                # get_thumbnail が None を返した場合 (キャッシュクラス内でエラーログが出力されているはず)
                logger.warning(f"サムネイル処理に失敗しました (None): {image_path}")
                return False
        except Exception as e:
            # get_thumbnail 内で捕捉されなかった予期せぬエラー
            logger.error(f"画像 '{image_path}' のサムネイル処理中に予期せぬエラー: {e}", exc_info=True)
            return False