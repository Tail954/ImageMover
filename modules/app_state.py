# \modules\app_state.py
# アプリケーション全体で共有される状態（コピーモード、ソート順、列数など）を管理するクラス。
from PyQt6.QtCore import QObject, pyqtSignal

class AppState(QObject):
    """アプリケーション全体の状態を管理するクラス"""

    # --- Signals ---
    copy_mode_changed = pyqtSignal(bool)
    sort_order_changed = pyqtSignal(str)
    thumbnail_columns_changed = pyqtSignal(int)

    def __init__(self, initial_sort="filename_asc", initial_columns=5):
        super().__init__()
        self._copy_mode = False
        self._current_sort = initial_sort
        self._thumbnail_columns = initial_columns

    # --- Properties ---
    @property
    def copy_mode(self):
        return self._copy_mode

    @copy_mode.setter
    def copy_mode(self, value):
        if self._copy_mode != value:
            self._copy_mode = value
            self.copy_mode_changed.emit(value)

    @property
    def current_sort(self):
        return self._current_sort

    @current_sort.setter
    def current_sort(self, value):
        # Note: ソート順変更のシグナルは現状未使用だが、将来のために用意
        if self._current_sort != value:
            self._current_sort = value
            self.sort_order_changed.emit(value)

    @property
    def thumbnail_columns(self):
        return self._thumbnail_columns

    @thumbnail_columns.setter
    def thumbnail_columns(self, value):
        if self._thumbnail_columns != value and value > 0: # 0以下は無効
            self._thumbnail_columns = value
            self.thumbnail_columns_changed.emit(value)
