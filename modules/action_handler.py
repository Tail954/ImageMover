# \modules\action_handler.py
# ユーザーインターフェースからのアクションを受け取り、関連する処理を実行する中心的なクラス。
import os
import sys # restart_application で使う
import json # save_last_values で使う
import logging # logging をインポート
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QApplication
from PyQt6.QtCore import QProcess # restart_application で使う
from modules.config import ConfigDialog, ConfigManager # ConfigManager をインポート
from modules.drop_window import DropWindow
from modules.wc_creator import WCCreatorDialog
from modules.thumbnail_widget import ImageThumbnail # select_all/unselect_all で型チェックに使う
from modules.image_loader import ImageLoader # ImageLoader をインポート
from modules.metadata import extract_metadata # メタデータ抽出関数をインポート
from modules.image_dialog import MetadataDialog, ImageDialog # ダイアログクラスをインポート
# 追加インポート
from modules.image_data_manager import ImageDataManager
from modules.file_manager import FileManager
from modules.thumbnail_cache import ThumbnailCache
from modules.ui_manager import UIManager # UIManager をインポート
from modules.thumbnail_view_controller import ThumbnailViewController # ThumbnailViewController をインポート

logger = logging.getLogger(__name__) # ロガーを取得

class ActionHandler:
    """
    ユーザーアクションやアプリケーションロジックの実行を担当するクラス。
    MainWindow や他のコンポーネントを操作する。
    """
    def __init__(self, main_window, app_state):
        self.main_window = main_window # MainWindow への参照は保持
        self.app_state = app_state
        self.image_loader = None # ImageLoaderインスタンスを保持

        # --- MainWindow から移動した属性 ---
        self.config_data = ConfigManager.load_config()
        self.current_folder = self.config_data.get("folder", "")
        self.cache_size = self.config_data.get("cache_size", 1000)
        self.preview_mode = self.config_data.get("preview_mode", "seamless")
        self.output_format = self.config_data.get("output_format", "separate_lines")
        self.metadata_dialog = None
        self.image_dialog = None
        self.drop_window = None
        # --- ここまで ---

        # --- ActionHandler が管理するコンポーネント ---
        self.thumbnail_cache = ThumbnailCache(max_size=self.cache_size) # Cache生成
        self.image_data_manager = ImageDataManager() # DataManager生成
        self.file_manager = FileManager() # FileManager生成
        self.ui_manager = None # UIManager は initialize_components で生成
        self.thumbnail_view_controller = None # ThumbnailViewController は initialize_components で生成
        # --- ここまで ---

    def initialize_components(self):
        """UIマネージャーとビューコントローラーを初期化し、シグナルを接続する"""
        # UIManager (UI要素の管理)
        self.ui_manager = UIManager(self.main_window, self.app_state)
        self.ui_manager.setup_ui() # UI要素を作成

        # ThumbnailViewController (サムネイル表示の管理)
        if hasattr(self.main_window, 'grid_layout') and hasattr(self.main_window, 'grid_widget'):
            # ActionHandler 自身を渡してキャッシュ等を取得させる
            self.thumbnail_view_controller = ThumbnailViewController(
                self.main_window.grid_layout, self.main_window.grid_widget, self # self (ActionHandler) を渡す
            )
        else:
            logger.error("grid_layout or grid_widget not initialized by UIManager.")

        # --- シグナル接続 ---
        # AppState -> UIManager
        if self.ui_manager:
            self.app_state.copy_mode_changed.connect(self.ui_manager._handle_copy_mode_change)
            self.app_state.thumbnail_columns_changed.connect(self.ui_manager._handle_thumbnail_columns_change)
        else:
            logger.error("UIManager not initialized when connecting AppState signals.")

        # ImageDataManager -> ActionHandler
        self.image_data_manager.images_updated.connect(self._handle_images_updated)

        # UIManager (UI要素 -> ActionHandler)
        if self.ui_manager:
            self.ui_manager._connect_signals() # UI要素のシグナルを接続
        # --- ここまで ---

    # --- UI Action Handlers ---
    def open_drop_window(self):
        """ドラッグアンドドロップ用の小さなウィンドウを開く"""
        if self.drop_window is None or not self.drop_window.isVisible():
            self.drop_window = DropWindow(self.main_window, self)
            self.drop_window.show()
            logger.info("ドロップウィンドウを開きました。")
        else:
            self.drop_window.raise_()
            self.drop_window.activateWindow()
            logger.info("ドロップウィンドウをアクティブにしました。")

    def open_config_dialog(self):
        """設定ダイアログを開く"""
        dialog = ConfigDialog(current_cache_size=self.cache_size,
                            current_preview_mode=self.preview_mode,
                            current_output_format=self.output_format,
                            parent=self.main_window)
        dialog.exec()

    def decrement_columns(self):
        """サムネイル列数を減らす"""
        self.app_state.thumbnail_columns -= 1

    def increment_columns(self):
        """サムネイル列数を増やす"""
        if self.app_state.thumbnail_columns < 20:
             self.app_state.thumbnail_columns += 1

    def toggle_folder_tree(self):
        """フォルダツリーの表示/非表示を切り替え、列数を調整する"""
        mw = self.main_window
        if hasattr(mw, 'tree_view') and mw.tree_view.isVisible():
            mw.tree_view.hide()
            if hasattr(mw, 'splitter'): mw.splitter.setSizes([0, 800])
            if hasattr(mw, 'toggle_button'): mw.toggle_button.setText(">>")
            self.app_state.thumbnail_columns += 1
        else:
            if hasattr(mw, 'tree_view'): mw.tree_view.show()
            if hasattr(mw, 'splitter'): mw.splitter.setSizes([250, 800])
            if hasattr(mw, 'toggle_button'): mw.toggle_button.setText("<<")
            self.app_state.thumbnail_columns -= 1

    def sort_images(self, sort_type):
        """指定されたタイプで画像をソートする"""
        mw = self.main_window
        if not self.ui_manager: return
        self.app_state.current_sort = sort_type
        current_state = {}
        if hasattr(mw, 'grid_layout'):
            for i in range(mw.grid_layout.count()):
                widget = mw.grid_layout.itemAt(i).widget()
                if widget and isinstance(widget, ImageThumbnail):
                    current_state[widget.image_path] = {"selected": widget.selected, "order": widget.order}
        self.ui_manager.saved_thumbnail_state = current_state
        self.image_data_manager.sort(self.app_state.current_sort)

    def filter_images(self):
        """フィルターボックスの内容に基づいて画像をフィルタリングする"""
        mw = self.main_window
        if not hasattr(mw, 'filter_box') or not self.ui_manager: return
        query = mw.filter_box.text()
        self.ui_manager.show_status_message("Filtering...")
        self.ui_manager.set_ui_enabled(False)
        QApplication.processEvents()

        if hasattr(mw, 'grid_layout'):
            current_state = {}
            for i in range(mw.grid_layout.count()):
                widget = mw.grid_layout.itemAt(i).widget()
                if widget and isinstance(widget, ImageThumbnail):
                    current_state[widget.image_path] = {"selected": widget.selected, "order": widget.order}
        self.ui_manager.saved_thumbnail_state = current_state

        mode_is_and = mw.and_radio.isChecked() if hasattr(mw, 'and_radio') else True
        terms = [term.strip().lower() for term in query.split(",") if term.strip()]
        self.image_data_manager.filter(terms, mode_is_and)

        self.ui_manager.set_ui_enabled(True)

    def toggle_copy_mode(self):
        """コピーモードを切り替える"""
        self.app_state.copy_mode = not self.app_state.copy_mode

    def select_all(self):
        """表示されているすべてのサムネイルを選択/全解除する"""
        mw = self.main_window
        if not hasattr(mw, 'grid_layout'): return
        all_selected = True
        for i in range(mw.grid_layout.count()):
            thumb = mw.grid_layout.itemAt(i).widget()
            if thumb and isinstance(thumb, ImageThumbnail):
                if not thumb.selected:
                    all_selected = False
                    thumb.selected = True
                    thumb.setStyleSheet("border: 3px solid orange;")
                    if self.app_state.copy_mode:
                        if self.thumbnail_view_controller and thumb not in self.thumbnail_view_controller.selection_order:
                            self.thumbnail_view_controller.selection_order.append(thumb)
                            thumb.order = len(self.thumbnail_view_controller.selection_order)
                            thumb.order_label.setText(str(thumb.order))
                            thumb.order_label.show()
        if all_selected:
            self.unselect_all()
        else:
            if self.ui_manager: self.ui_manager.update_selected_count()

    def unselect_all(self):
        """すべてのサムネイルの選択を解除する"""
        mw = self.main_window
        if not hasattr(mw, 'grid_layout'): return
        for i in range(mw.grid_layout.count()):
            thumb = mw.grid_layout.itemAt(i).widget()
            if thumb and isinstance(thumb, ImageThumbnail):
                thumb.selected = False
                thumb.setStyleSheet("")
                thumb.order = -1
                thumb.order_label.hide()
        if self.thumbnail_view_controller:
            self.thumbnail_view_controller.clear_selection_order()
        if self.ui_manager: self.ui_manager.update_selected_count()

    def move_images(self):
        """選択された画像を移動する"""
        mw = self.main_window
        if not hasattr(mw, 'grid_layout') or not self.ui_manager:
            QMessageBox.warning(mw, "Error", "UI not fully initialized.")
            return
        selected_thumbs = [mw.grid_layout.itemAt(i).widget()
                           for i in range(mw.grid_layout.count())
                           if isinstance(mw.grid_layout.itemAt(i).widget(), ImageThumbnail) and mw.grid_layout.itemAt(i).widget().selected]
        if not selected_thumbs:
            QMessageBox.warning(mw, "No Selection", "Please select images to move.")
            return
        destination_folder = QFileDialog.getExistingDirectory(mw, "Select Destination Folder")
        if not destination_folder: return

        self.ui_manager.set_ui_enabled(False)
        self.ui_manager.show_status_message("Moving images...")
        QApplication.processEvents()

        source_paths = [thumb.image_path for thumb in selected_thumbs]
        result = self.file_manager.move_files(source_paths, destination_folder)

        successful_moves = set(source_paths)
        for error_msg in result['errors']:
             failed_file = None
             if "Error moving" in error_msg:
                 try:
                     failed_file_basename = error_msg.split("Error moving ")[1].split(":")[0].strip()
                     for sp in source_paths:
                         if os.path.basename(sp) == failed_file_basename: failed_file = sp; break
                 except IndexError: pass
             elif "Source file not found" in error_msg:
                 try:
                     failed_file_basename = error_msg.split("Source file not found: ")[1].strip()
                     for sp in source_paths:
                         if os.path.basename(sp) == failed_file_basename: failed_file = sp; break
                 except IndexError: pass
             if failed_file: successful_moves.discard(failed_file)

        self.image_data_manager.remove_paths(successful_moves)
        for path in successful_moves:
            self.thumbnail_cache.remove(path)

        self.image_data_manager.sort(self.app_state.current_sort)

        self.ui_manager.set_ui_enabled(True)
        self.unselect_all()

        if self.current_folder and os.path.exists(self.current_folder):
            self.check_and_remove_empty_folders(self.current_folder)
        self.check_and_remove_empty_folders(destination_folder)

        if result['errors']: QMessageBox.warning(mw, "Move Errors", "Some errors occurred during move:\n" + "\n".join(result['errors']))
        if result['renamed_files']: QMessageBox.information(mw, "Renamed Files", "Renamed due to duplicates:\n" + "\n".join(result['renamed_files']))

    def copy_images(self):
        """選択順に画像をコピーする"""
        mw = self.main_window
        if not self.ui_manager: return
        selection_order_list = self.thumbnail_view_controller.get_selection_order() if self.thumbnail_view_controller else []
        if not selection_order_list:
            QMessageBox.warning(mw, "No Selection Order", "Please select images in order for copy mode.")
            return
        destination_folder = QFileDialog.getExistingDirectory(mw, "Select Destination Folder")
        if not destination_folder: return

        self.ui_manager.set_ui_enabled(False)
        self.ui_manager.show_status_message("Copying images...")
        QApplication.processEvents()

        ordered_source_paths = [thumb.image_path for thumb in selection_order_list]
        result = self.file_manager.copy_files(ordered_source_paths, destination_folder)

        self.ui_manager.set_ui_enabled(True)
        self.unselect_all()

        status_msg = f"Copied {result['copied_count']} images."
        if result['errors']: status_msg += f" ({len(result['errors'])} errors)"
        self.ui_manager.show_status_message(status_msg)

        self.check_and_remove_empty_folders(destination_folder)
        if result['errors']: QMessageBox.warning(mw, "Copy Errors", "Some errors occurred during copy:\n" + "\n".join(result['errors']))

    def open_wc_creator(self):
        """WC Creatorダイアログを開く"""
        mw = self.main_window
        if not hasattr(mw, 'grid_layout'):
            QMessageBox.warning(mw, "Error", "Thumbnail grid not initialized.")
            return
        selected_thumbs = [mw.grid_layout.itemAt(i).widget()
                           for i in range(mw.grid_layout.count())
                           if isinstance(mw.grid_layout.itemAt(i).widget(), ImageThumbnail) and mw.grid_layout.itemAt(i).widget().selected]
        if not selected_thumbs:
            QMessageBox.warning(mw, "No Selection", "Please select at least one image first.")
            return
        selected_images = [thumb.image_path for thumb in selected_thumbs]
        dialog = WCCreatorDialog(selected_images, self.thumbnail_cache, self.output_format, mw)
        dialog.exec()

    # --- Dialog Showing Methods ---
    def show_metadata_dialog(self, image_path):
        """画像パスを受け取り、メタデータダイアログを表示または更新する"""
        mw = self.main_window
        try:
            metadata = extract_metadata(image_path)
            if not metadata:
                 QMessageBox.warning(mw, "メタデータエラー", f"ファイルからメタデータを取得できませんでした:\n{os.path.basename(image_path)}")
                 return
            if self.metadata_dialog and self.metadata_dialog.isVisible():
                self.metadata_dialog.update_metadata(metadata)
                self.metadata_dialog.raise_()
                self.metadata_dialog.activateWindow()
            else:
                self.metadata_dialog = MetadataDialog(metadata, mw)
                self.metadata_dialog.setModal(False)
                self.metadata_dialog.show()
                self.metadata_dialog.raise_()
                self.metadata_dialog.activateWindow()
        except FileNotFoundError:
             QMessageBox.critical(mw, "ファイルエラー", f"指定されたファイルが見つかりません:\n{image_path}")
        except Exception as e:
            QMessageBox.critical(mw, "エラー", f"メタデータ表示中に予期せぬエラーが発生しました:\n{e}")
            logger.exception("メタデータ表示中に予期せぬエラーが発生しました") # 修正: print -> logger.exception

    def show_image_dialog(self, image_path):
        """画像パスを受け取り、画像プレビューダイアログを表示または更新する"""
        mw = self.main_window
        try:
            if self.image_dialog and self.image_dialog.isVisible():
                current_image_list = self.image_data_manager.get_displayed_images()
                self.image_dialog.load_image(image_path)
                self.image_dialog.raise_()
                self.image_dialog.activateWindow()
            else:
                current_image_list = self.image_data_manager.get_displayed_images()
                self.image_dialog = ImageDialog(image_path, self.preview_mode, mw)
                self.image_dialog.setModal(False)
                self.image_dialog.show()
                self.image_dialog.raise_()
                self.image_dialog.activateWindow()
        except FileNotFoundError:
             QMessageBox.critical(mw, "ファイルエラー", f"指定されたファイルが見つかりません:\n{image_path}")
        except Exception as e:
            QMessageBox.critical(mw, "エラー", f"画像プレビュー表示中に予期せぬエラーが発生しました:\n{e}")
            logger.exception("画像プレビュー表示中に予期せぬエラーが発生しました") # 修正: print -> logger.exception

    # --- Event Handlers ---
    def on_folder_selected(self, index):
        """ツリービューでフォルダが選択されたときの処理"""
        mw = self.main_window
        if hasattr(mw, 'folder_model'):
            folder_path = mw.folder_model.filePath(index)
            if os.path.isdir(folder_path):
                self.current_folder = folder_path
                if hasattr(mw, 'filter_box'): mw.filter_box.clear()
                self.check_and_remove_empty_folders(folder_path)
                self.load_images_from_folder(folder_path)
            else:
                logger.warning(f"Selected path is not a directory: {folder_path}") # 修正: print -> logger.warning

    def finalize_loading(self, images):
        """画像読み込み完了後の処理 (ImageLoaderから呼ばれる)"""
        mw = self.main_window
        if hasattr(mw, 'filter_box'): mw.filter_box.clear()
        self.image_data_manager.set_images(images)
        self.image_data_manager.sort(self.app_state.current_sort)
        loaded_images = self.image_data_manager.get_displayed_images()
        missing_files = [img for img in images if not os.path.exists(img)]
        if missing_files:
            logger.warning(f"Missing files after loading: {missing_files}") # 修正: print -> logger.warning

        if self.ui_manager:
            self.ui_manager.set_ui_enabled(True)
            if not loaded_images:
                self.ui_manager.show_status_message("No images found in this folder.")
            else:
                self.ui_manager.update_selected_count()

    def handle_close(self):
        """ウィンドウ終了時の処理 (MainWindow.closeEventから呼ばれる)"""
        if self.drop_window and self.drop_window.isVisible():
            self.drop_window.close()
        if self.metadata_dialog and self.metadata_dialog.isVisible():
            self.metadata_dialog.close()
        if self.image_dialog and self.image_dialog.isVisible():
            self.image_dialog.close()
        self.save_last_values()

    def restart_application(self):
        """アプリケーションを再起動する"""
        mw = self.main_window
        mw.close()
        QApplication.processEvents()
        QProcess.startDetached(sys.executable, sys.argv)

    def on_thumbnail_double_clicked(self, thumb_widget):
        """サムネイルがダブルクリックされたときの処理"""
        self.show_image_dialog(thumb_widget.image_path)

    # --- Signal Handlers / Slots ---

    def _handle_images_updated(self, image_list):
        """ImageDataManagerからの更新通知を受けて、ViewControllerに表示更新を依頼する"""
        if self.thumbnail_view_controller and self.ui_manager:
            self.thumbnail_view_controller.update_display(
                image_list,
                self.app_state.thumbnail_columns,
                self.ui_manager.saved_thumbnail_state,
                self.app_state.copy_mode
            )
            self.ui_manager.saved_thumbnail_state = {}

    # --- Other Logic ---
    def save_last_values(self):
        """アプリケーション終了時に設定を保存する"""
        mw = self.main_window
        temp_columns = self.app_state.thumbnail_columns
        if hasattr(mw, 'tree_view') and not mw.tree_view.isVisible():
            temp_columns = self.app_state.thumbnail_columns - 1 if self.app_state.thumbnail_columns > 1 else 1
        self.config_data["folder"] = self.current_folder
        self.config_data["thumbnail_columns"] = temp_columns
        self.config_data["cache_size"] = self.cache_size
        self.config_data["sort_order"] = self.app_state.current_sort
        self.config_data["preview_mode"] = self.preview_mode
        self.config_data["output_format"] = self.output_format
        ConfigManager.save_config(self.config_data)

    def update_config(self, new_cache_size, new_preview_mode, new_output_format):
        """設定変更を適用する"""
        mw = self.main_window
        if self.cache_size != new_cache_size:
            self.cache_size = new_cache_size
            self.thumbnail_cache.resize(new_cache_size)
        self.preview_mode = new_preview_mode
        self.output_format = new_output_format
        self.save_last_values()
        QMessageBox.information(mw, "Settings Updated",
                        f"Cache size: {self.cache_size}\n"
                        f"Preview mode: {self.preview_mode}\n"
                        f"Output format: {'Separate lines' if self.output_format == 'separate_lines' else 'Inline [:100]'}")

    def check_and_remove_empty_folders(self, folder):
        """空フォルダをチェックして削除する"""
        mw = self.main_window
        try:
            empty_folders = self.file_manager.find_empty_folders(folder)
            if not empty_folders: return
            folders_str = "\n".join(empty_folders)
            reply = QMessageBox.question(mw, '空のフォルダが見つかりました',
                                         f'以下の空フォルダが見つかりました。ゴミ箱に移動しますか？\n\n{folders_str}',
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                result = self.file_manager.remove_folders_to_trash(empty_folders)
                if result['errors']: QMessageBox.warning(mw, "削除エラー", f"{len(result['errors'])} 個のフォルダ削除中にエラーが発生しました:\n" + "\n".join(result['errors']))
                if result['deleted_count'] > 0: QMessageBox.information(mw, "削除完了", f"{result['deleted_count']} 個の空フォルダをゴミ箱に移動しました。")
        except ImportError:
            QMessageBox.warning(mw, "依存関係エラー", "send2trash ライブラリが見つかりません。\n空フォルダの自動削除機能は無効になります。\n`pip install Send2Trash` でインストールしてください。")
        except Exception as e:
            QMessageBox.critical(mw, "エラー", f"空フォルダのチェック中に予期せぬエラーが発生しました:\n{e}")
            logger.exception("空フォルダのチェック中に予期せぬエラーが発生しました") # 修正: print -> logger.exception

    def load_images(self):
        """画像フォルダ選択ダイアログを開き、画像を読み込む"""
        mw = self.main_window
        initial_dir = self.current_folder if self.current_folder and os.path.isdir(self.current_folder) else ""
        folder = QFileDialog.getExistingDirectory(mw, "Select Image Folder", initial_dir)
        if folder:
            self.current_folder = folder
            if self.ui_manager: self.ui_manager.update_folder_tree_view(folder)
            self.check_and_remove_empty_folders(folder)
            self.load_images_from_folder(folder)

    def load_images_from_folder(self, folder):
        """指定されたフォルダから画像を非同期で読み込む"""
        mw = self.main_window
        if not self.ui_manager: return
        self.ui_manager.show_status_message(f"Loading images from: {folder}...")
        if self.thumbnail_view_controller:
            self.thumbnail_view_controller.clear_thumbnails()
        self.ui_manager.set_ui_enabled(False)
        if self.image_loader and self.image_loader.isRunning():
            self.image_loader.stop()
            self.image_loader.wait()
        self.image_loader = ImageLoader(folder, self.thumbnail_cache)
        self.image_loader.update_progress.connect(self.ui_manager.update_image_count)
        self.image_loader.finished_loading.connect(self.finalize_loading)
        self.image_loader.start()

    # --- Thumbnail Click Handler ---
    def on_thumbnail_clicked(self, thumb_widget):
        """サムネイルがクリックされたときの処理"""
        mw = self.main_window
        if self.app_state.copy_mode:
            if not self.thumbnail_view_controller: return
            selection_order_list = self.thumbnail_view_controller.selection_order
            if thumb_widget.selected:
                thumb_widget.selected = False
                thumb_widget.setStyleSheet("")
                order_to_remove = thumb_widget.order
                thumb_widget.order = -1
                thumb_widget.order_label.hide()
                if thumb_widget in selection_order_list:
                    selection_order_list.remove(thumb_widget)
                    for i, thumb in enumerate(selection_order_list):
                        new_order = i + 1
                        if thumb.order != new_order:
                            thumb.order = new_order
                            thumb.order_label.setText(str(thumb.order))
            else:
                thumb_widget.selected = True
                thumb_widget.setStyleSheet("border: 3px solid orange;")
                selection_order_list.append(thumb_widget)
                thumb_widget.order = len(selection_order_list)
                thumb_widget.order_label.setText(str(thumb_widget.order))
                thumb_widget.order_label.show()
        else:
            thumb_widget.selected = not thumb_widget.selected
            thumb_widget.setStyleSheet("border: 3px solid orange;" if thumb_widget.selected else "")
        if self.ui_manager: self.ui_manager.update_selected_count()
