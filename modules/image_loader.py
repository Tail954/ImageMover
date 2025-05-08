# modules/image_loader.py
# 指定されたフォルダから画像を非同期で読み込み、サムネイル生成をトリガーするクラス。
import concurrent.futures
import logging # logging をインポート
import time # time をインポート
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__) # ロガーを取得
SUPPORTED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']

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
        # SUPPORTED_EXTENSIONS を使用するように変更
        self.valid_extensions = {ext.lower() for ext in SUPPORTED_EXTENSIONS}


    def stop(self):
        self._is_running = False
        self.wait()

    def is_valid_image(self, file_path):
        return Path(file_path).suffix.lower() in self.valid_extensions

    def run(self):
        logger.info(f"Starting to load images from folder: {self.folder}")
        overall_start_time = time.time()
        processed_image_count = 0
        try:
            # glob を使って再帰的にファイルを取得
            all_files_in_folder = [str(f) for f in Path(self.folder).rglob('*') if f.is_file()]
            image_files_to_process = [f for f in all_files_in_folder if self.is_valid_image(f)]
            self.total_files = len(image_files_to_process)
            logger.info(f"Found {self.total_files} image files to process in {self.folder}.")

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                future_to_path = {
                    executor.submit(self.process_image, path): path
                    for path in image_files_to_process
                }
                for i, future in enumerate(concurrent.futures.as_completed(future_to_path)):
                    if not self._is_running:
                        logger.info("Image loading process was stopped.")
                        break
                    path = future_to_path[future]
                    try:
                        if future.result(): # process_image が True を返した場合
                            self.images.append(path)
                            # update_thumbnail はインデックスではなく、パスと処理済みカウントを渡す方が良いかもしれない
                            # ここでは元のiを維持するが、UI側での扱いを検討
                            self.update_thumbnail.emit(path, len(self.images) -1) # 実際にリストに追加されたインデックス
                            processed_image_count +=1
                        else:
                            logger.warning(f"process_image returned False for {path}")
                    except Exception as e_future:
                        logger.error(f"Error processing future for {path}: {e_future}", exc_info=True)
                    self.update_progress.emit(i + 1, self.total_files)

            if self._is_running:
                overall_duration_ms = (time.time() - overall_start_time) * 1000
                logger.info(f"Finished loading {processed_image_count} images from {self.folder}. Total time: {overall_duration_ms:.2f} ms")
                self.finished_loading.emit(self.images)
            else:
                logger.info(f"Image loading stopped. Processed {processed_image_count} images from {self.folder}.")
                self.finished_loading.emit(self.images) # 途中までの結果を通知

        except Exception as e:
            logger.error(f"Error occurred in image loader run method for folder {self.folder}: {e}", exc_info=True)
            if self._is_running: # エラー発生時もシグナルを出す
                self.finished_loading.emit(self.images)


    def process_image(self, image_path):
        """個々の画像ファイルを処理し、サムネイルキャッシュを試みる。"""
        process_start_time = time.time()
        logger.debug(f"Processing image: {image_path}")
        try:
            # サムネイルキャッシュのキーはキャッシュクラス側で生成されるべきだが、
            # ここではキャッシュの存在確認のために同様のロジックを使う
            # cache_key = f"{image_path}_{self.thumbnail_size}"
            # if cache_key in self.thumbnail_cache.cache: # 直接キャッシュ辞書にアクセスするのは避けるべき
            #     logger.debug(f"Thumbnail for {image_path} likely in cache (not checked directly).")
            #     # キャッシュにあっても、get_thumbnailを呼んでQPixmapオブジェクトを取得する必要がある場合がある
            #     # ここでは、サムネイル生成を試みることでキャッシュの利用を促す
            
            # サムネイル生成/取得を試みる
            # get_thumbnail は QPixmap を返すので、ここでは成功したかどうかだけを判定
            pixmap = self.thumbnail_cache.get_thumbnail(image_path, self.thumbnail_size)
            duration_ms = (time.time() - process_start_time) * 1000
            if pixmap:
                logger.debug(f"Successfully processed (got/generated thumbnail for) {image_path} in {duration_ms:.2f} ms.")
                return True
            else:
                logger.warning(f"Failed to get/generate thumbnail for {image_path} in {duration_ms:.2f} ms.")
                return False
        except Exception as e:
            duration_ms = (time.time() - process_start_time) * 1000
            logger.error(f"Error processing image {image_path} in {duration_ms:.2f} ms: {e}", exc_info=True)
            return False

