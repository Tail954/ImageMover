# g:\vscodeGit\modules\image_data_manager.py
import os
from PyQt6.QtCore import QObject, pyqtSignal
from modules.metadata import extract_metadata # メタデータ抽出関数をインポート

class ImageDataManager(QObject):
    """
    画像データのリスト管理、フィルタリング、ソートを担当するクラス。
    UIとは独立して動作し、データの変更をシグナルで通知する。
    """
    images_updated = pyqtSignal(list) # 表示すべき画像リストが更新されたことを通知するシグナル

    def __init__(self):
        super().__init__()
        self._all_images = []       # フォルダから読み込んだ全ての画像パス
        self._displayed_images = [] # 現在フィルタリング/ソートされて表示対象となっている画像パス
        self._current_sort = "filename_asc" # 現在のソート順

    def set_images(self, image_paths):
        """新しい画像リストを設定し、初期ソートを適用して通知する"""
        self._all_images = [img for img in image_paths if os.path.exists(img)] # 存在するものだけ保持
        # フィルタリングされていない状態なので、表示リストも全画像リストと同じにする
        self._displayed_images = list(self._all_images)
        self.sort(self._current_sort) # 初期リストでソートを実行（これにより _displayed_images が更新され、シグナルが発行される）

    def get_displayed_images(self):
        """現在表示対象の画像リストを返す"""
        return self._displayed_images

    def filter(self, terms, mode_is_and):
        """
        画像リストをフィルタリングし、結果をソートして通知する。
        Args:
            terms (list[str]): フィルタリングキーワードのリスト。
            mode_is_and (bool): TrueならAND検索、FalseならOR検索。
        """
        if not terms:
            # フィルタが空なら全画像を表示対象とする
            self._displayed_images = list(self._all_images) # コピーを作成
        else:
            matches = []
            for image_path in self._all_images: # 常に全画像からフィルタリング
                try:
                    # ここでメタデータを抽出する（キャッシュがあれば効率的だが、現状は都度抽出）
                    metadata_str = extract_metadata(image_path)
                    if metadata_str is None:
                        metadata_str = ""
                    metadata_str_lower = metadata_str.lower()

                    if mode_is_and:
                        if all(term in metadata_str_lower for term in terms):
                            matches.append(image_path)
                    else: # OR
                        if any(term in metadata_str_lower for term in terms):
                            matches.append(image_path)
                except Exception as e:
                    print(f"Error extracting metadata for {os.path.basename(image_path)} during filter: {e}")
                    continue
            self._displayed_images = matches

        # フィルタリング後、現在のソート順を適用
        self.sort(self._current_sort, emit_signal=True) # ソート結果でシグナル発行

    def sort(self, sort_type, emit_signal=True):
        """表示対象の画像リストをソートし、必要なら通知する"""
        self._current_sort = sort_type
        images_to_sort = self._displayed_images # 現在表示されているリストをソート

        # ソート前に存在確認（より安全に）
        valid_images_to_sort = [img for img in images_to_sort if os.path.exists(img)]

        if sort_type == "filename_asc":
            self._displayed_images = sorted(valid_images_to_sort, key=lambda x: os.path.basename(x).lower())
        elif sort_type == "filename_desc":
            self._displayed_images = sorted(valid_images_to_sort, key=lambda x: os.path.basename(x).lower(), reverse=True)
        elif sort_type == "date_asc":
            self._displayed_images = sorted(valid_images_to_sort, key=lambda x: os.path.getmtime(x))
        else:  # date_desc
            self._displayed_images = sorted(valid_images_to_sort, key=lambda x: os.path.getmtime(x), reverse=True)

        if emit_signal:
            self.images_updated.emit(list(self._displayed_images)) # 更新されたリストのコピーをシグナルで送る

    def remove_paths(self, paths_to_remove):
        """指定されたパスを内部リストから削除する"""
        path_set = set(paths_to_remove)
        self._all_images = [img for img in self._all_images if img not in path_set]
        self._displayed_images = [img for img in self._displayed_images if img not in path_set]
        # 削除後、表示リストを再送する必要があればシグナルを発行しても良いが、
        # move_images 内で明示的に再描画しているのでここでは不要かも
        # self.images_updated.emit(list(self._displayed_images))
