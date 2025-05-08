# \modules\thumbnail_view_controller.py
# サムネイル表示グリッドの更新、クリア、選択状態の管理を行うクラス。
from PyQt6.QtWidgets import QWidget, QLabel, QApplication # QApplication をインポート
from PyQt6.QtCore import Qt # Qt をインポート (No images message)
from modules.thumbnail_widget import ImageThumbnail
import logging # logging をインポート
import os # os.path.basename のため
import time # time をインポート

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
        self.app_state = action_handler.app_state # AppState も取得

        if not self.ui_manager:
            logger.error("UIManager not found via ActionHandler.")
        if not self.thumbnail_cache:
            logger.error("ThumbnailCache is not found via ActionHandler.")
        if not self.app_state:
            logger.error("AppState is not found via ActionHandler.")


    def clear_thumbnails(self):
        """グリッド上の全てのサムネイルウィジェットを削除する"""
        logger.debug("Clearing all thumbnails from the grid.")
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.selection_order.clear() # 選択順序もクリア

    def _show_no_images_message(self):
        """画像がない場合にメッセージを表示する"""
        # 既存のウィジェットをクリア
        self.clear_thumbnails()
        no_images_label = QLabel("No images to display in this folder or filter.")
        no_images_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # レイアウトの中央に配置するために、ストレッチアイテムを追加することも検討できる
        self.grid_layout.addWidget(no_images_label, 0, 0, 1, self.app_state.thumbnail_columns if self.app_state else 1)


    def update_display(self, image_list, columns, saved_state, copy_mode):
        """
        指定された画像リストと状態に基づいてサムネイルグリッドを更新する
        Args:
            image_list (list[str]): 表示する画像パスのリスト
            columns (int): 表示する列数
            saved_state (dict): UIManagerが保持するサムネイルの状態 (選択状態や順序)
            copy_mode (bool): 現在のコピーモード
        """
        logger.info(f"Starting to update display with {len(image_list)} images, {columns} columns. Copy mode: {copy_mode}")
        overall_start_time = time.time()

        if not self.thumbnail_cache:
            logger.error("ThumbnailCache is not available in ThumbnailViewController. Cannot update display.")
            return
        if not self.app_state: # columns を取得するために必要
            logger.error("AppState is not available in ThumbnailViewController. Cannot update display.")
            return

        # logger.debug("Clearing existing thumbnails...")
        clear_start_time = time.time()
        self.clear_thumbnails() # まず既存のサムネイルをクリア
        clear_duration_ms = (time.time() - clear_start_time) * 1000
        # logger.debug(f"Cleared existing thumbnails in {clear_duration_ms:.2f} ms.")

        if not image_list:
            self._show_no_images_message()
            logger.info("No images to display. Showing message.")
            overall_duration_ms = (time.time() - overall_start_time) * 1000
            logger.info(f"Finished updating display (no images). Total time: {overall_duration_ms:.2f} ms.")
            return

        row, col = 0, 0
        processed_count = 0
        new_selection_order_map = {} # コピーモード時の選択順序復元用 (クリア後に移動)
        for i, image_path in enumerate(image_list):
            loop_iter_start_time = time.time()
            if image_path is None: # 念のためチェック
                logger.warning(f"Encountered None image_path at index {i}. Skipping.")
                continue

            widget_creation_start_time = time.time()
            try:
                # ImageThumbnail のコンストラクタ内でサムネイル取得が行われる
                # logger.debug(f"Attempting to create ImageThumbnail for: {os.path.basename(image_path)}")
                thumb = ImageThumbnail(image_path, self.thumbnail_cache, self.grid_widget)
                # シグナル接続は ActionHandler のメソッドへ
                thumb.clicked.connect(self.action_handler.on_thumbnail_clicked)
                thumb.doubleClicked.connect(self.action_handler.on_thumbnail_double_clicked)
                # logger.debug(f"ImageThumbnail created for {os.path.basename(image_path)}")

                if image_path in saved_state:
                    state = saved_state[image_path]
                    if state.get('selected', False): # selected キーが存在しない場合も考慮
                        # logger.debug(f"Restoring selected state for {os.path.basename(image_path)}")
                        thumb.selected = True
                        thumb.setStyleSheet("border: 3px solid orange;") # 選択時のスタイル
                        if copy_mode and state.get('order', -1) > 0: # order キーが存在しない場合も考慮
                            # logger.debug(f"Restoring order {state['order']} for {os.path.basename(image_path)}")
                            thumb.order = state['order']
                            thumb.order_label.setText(str(thumb.order))
                            thumb.order_label.show()
                            new_selection_order_map[thumb.order] = thumb
                
                widget_creation_duration_ms = (time.time() - widget_creation_start_time) * 1000
                # logger.debug(f"Successfully configured thumbnail widget for {os.path.basename(image_path)} in {widget_creation_duration_ms:.2f} ms.")

                add_widget_start_time = time.time()
                # logger.debug(f"Attempting to add widget for {os.path.basename(image_path)} to layout.")
                self.grid_layout.addWidget(thumb, row, col)
                add_widget_duration_ms = (time.time() - add_widget_start_time) * 1000
                # logger.debug(f"Added widget for {os.path.basename(image_path)} to layout in {add_widget_duration_ms:.2f} ms.")

            except Exception as e:
                widget_creation_duration_ms = (time.time() - widget_creation_start_time) * 1000
                logger.error(f"CRITICAL ERROR during widget creation or layout add for {image_path} (iteration {i}) in {widget_creation_duration_ms:.2f} ms: {e}", exc_info=True)
                # この時点で異常終了する可能性があるので、できるだけ多くの情報をログに残す
                # エラーが発生した場合、プレースホルダー的なものを表示することも検討                
                error_label = QLabel(f"Error:\n{os.path.basename(image_path)}")
                error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                error_label.setWordWrap(True)
                error_label.setStyleSheet("border: 1px solid red; color: red;")
                self.grid_layout.addWidget(error_label, row, col)

            col += 1
            if col >= columns:
                col = 0
                row += 1

            processed_count += 1
            if processed_count % 500 == 0: # 500個処理するごとにログとUIイベント処理 (以前は250)
                status_message = f"Displaying thumbnails: {processed_count}/{len(image_list)}"
                # logger.info(f"{status_message}. Last: {os.path.basename(image_path)}. Processing UI events...")
                if self.ui_manager:
                    self.ui_manager.show_status_message(status_message) # ステータスバーに進捗を表示
                QApplication.processEvents() # UIの応答性を保つため
                # logger.debug(f"Finished processing UI events after {processed_count} items.")


            loop_iter_duration_ms = (time.time() - loop_iter_start_time) * 1000
            # logger.debug(f"Loop iteration {i} for {os.path.basename(image_path)} took {loop_iter_duration_ms:.2f} ms.")
        # コピーモード時の選択順序を復元
        if copy_mode and new_selection_order_map:
            self.selection_order = [new_selection_order_map[k] for k in sorted(new_selection_order_map.keys())]
        else:
            self.selection_order = [] # コピーモードでない、または復元対象がない場合はクリア

        # UIManager のメソッドを呼ぶ (選択数の更新など)
        if self.ui_manager:
            self.ui_manager.update_selected_count()
        
        overall_duration_ms = (time.time() - overall_start_time) * 1000
        logger.info(f"Finished updating display with {len(image_list)} images. Total time: {overall_duration_ms:.2f} ms.")


    def get_selection_order(self):
        """現在の選択順序リストを返す"""
        return self.selection_order

    def clear_selection_order(self):
        """選択順序リストをクリアする"""
        logger.debug("Clearing selection order list.")
        self.selection_order = []
