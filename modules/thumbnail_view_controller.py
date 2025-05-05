# \modules\thumbnail_view_controller.py
# サムネイル表示グリッドの更新、クリア、選択状態の管理を行うクラス。
from PyQt6.QtWidgets import QWidget
from modules.thumbnail_widget import ImageThumbnail
import logging # logging をインポート

logger = logging.getLogger(__name__) # ロガーを取得

class ThumbnailViewController:
    """サムネイルグリッドの表示更新を担当するクラス"""

    def __init__(self, grid_layout, grid_widget, action_handler): # main_window の代わりに action_handler を受け取る
        self.grid_layout = grid_layout
        self.grid_widget = grid_widget
        self.action_handler = action_handler # ActionHandler の参照を保持
        self.main_window = action_handler.main_window # MainWindow への参照は ActionHandler 経由で取得
        self.selection_order = []
        # UIManager と ThumbnailCache を ActionHandler から取得
        self.ui_manager = action_handler.ui_manager
        self.thumbnail_cache = action_handler.thumbnail_cache

        if not self.ui_manager:
            logger.error("UIManager not found via ActionHandler.")
        if not self.thumbnail_cache:
            logger.error("ThumbnailCache not found via ActionHandler.")


    def clear_thumbnails(self):
        """グリッド上の全てのサムネイルウィジェットを削除する"""
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def update_display(self, image_list, columns, saved_state, copy_mode):
        """
        指定された画像リストと状態に基づいてサムネイルグリッドを更新する
        Args:
            saved_state (dict): UIManagerが保持するサムネイルの状態
        """
        if not self.thumbnail_cache:
            logger.error("ThumbnailCache is not available in ThumbnailViewController.")
            return

        self.clear_thumbnails()
        new_selection_order_map = {}

        for i, image_path in enumerate(image_list):
            # self.thumbnail_cache を使う
            thumb = ImageThumbnail(image_path, self.thumbnail_cache, self.grid_widget)
            # シグナル接続は ActionHandler のメソッドへ
            thumb.clicked.connect(self.action_handler.on_thumbnail_clicked)
            thumb.doubleClicked.connect(self.action_handler.on_thumbnail_double_clicked)

            if image_path in saved_state:
                state = saved_state[image_path]
                if state['selected']:
                    thumb.selected = True
                    thumb.setStyleSheet("border: 3px solid orange;")
                    if copy_mode and state['order'] > 0:
                        thumb.order = state['order']
                        thumb.order_label.setText(str(thumb.order))
                        thumb.order_label.show()
                        new_selection_order_map[thumb.order] = thumb

            row = i // columns
            col = i % columns
            self.grid_layout.addWidget(thumb, row, col)

        self.selection_order = [new_selection_order_map[k] for k in sorted(new_selection_order_map)]

        # UIManager のメソッドを呼ぶ
        if self.ui_manager:
            self.ui_manager.update_selected_count()
        # else: # フォールバックは不要になったはず
        #     if hasattr(self.main_window, 'update_selected_count'):
        #          self.main_window.update_selected_count()


    def get_selection_order(self):
        """現在の選択順序リストを返す"""
        return self.selection_order

    def clear_selection_order(self):
        """選択順序リストをクリアする"""
        self.selection_order = []
