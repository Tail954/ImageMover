# g:\vscodeGit\modules\thumbnail_widget.py
import os
from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt, pyqtSignal # pyqtSignal をインポート
from modules.metadata import extract_metadata

THUMBNAIL_SIZE = 200 # 定数として定義 (元のコードにはなかったが、サイズ指定がハードコードされていたため)

class ImageThumbnail(QLabel):
    # クリックシグナルを定義
    clicked = pyqtSignal(object) # 自分自身 (ImageThumbnail インスタンス) を渡すシグナル
    doubleClicked = pyqtSignal(object) # ダブルクリックシグナルも定義

    def __init__(self, image_path, thumbnail_cache, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.thumbnail_cache = thumbnail_cache
        self.selected = False
        self.order = -1
        self.setFixedSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE) # 定数を使用
        self.setScaledContents(False) # アスペクト比を維持するため False が適切
        self.setAlignment(Qt.AlignmentFlag.AlignCenter) # 中央揃えを追加
        self.load_thumbnail()
        self.setToolTip(os.path.dirname(image_path)) # ツールチップはフォルダパス

        # 選択順序表示用ラベル
        self.order_label = QLabel(self)
        self.order_label.setStyleSheet("color: white; background-color: rgba(0, 0, 0, 180); border-radius: 5px; padding: 2px;") # スタイル調整
        self.order_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.order_label.setFixedSize(30, 20) # サイズ調整
        self.order_label.move(5, 5) # 左上に配置
        self.order_label.hide()

    def load_thumbnail(self):
        try:
            # キャッシュからサムネイルを取得
            pixmap = self.thumbnail_cache.get_thumbnail(self.image_path, THUMBNAIL_SIZE)
            if pixmap:
                # QLabelのサイズに合わせてスケーリング（アスペクト比維持）
                scaled_pixmap = pixmap.scaled(
                    self.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.setPixmap(scaled_pixmap)
            else:
                self.setText("Error") # エラーテキスト表示
        except Exception as e:
            print(f"Error loading thumbnail for {os.path.basename(self.image_path)}: {e}")
            self.setText("Load Fail") # 失敗テキスト表示

    def mousePressEvent(self, event):
        """マウスボタンが押されたときのイベント"""
        if event.button() == Qt.MouseButton.LeftButton:
            # clicked シグナルを発行 (ActionHandler側で処理するように変更)
            self.clicked.emit(self)
        elif event.button() == Qt.MouseButton.RightButton:
            # 右クリックでメタデータダイアログ表示 (ActionHandler経由)
            main_window = self.get_main_window()
            if main_window and hasattr(main_window, 'action_handler') and main_window.action_handler:
                main_window.action_handler.show_metadata_dialog(self.image_path)
            else:
                print("Error: Could not find MainWindow or ActionHandler for metadata dialog.")
        # 親クラスのイベント処理も呼び出す
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """マウスがダブルクリックされたときのイベント"""
        if event.button() == Qt.MouseButton.LeftButton:
            # doubleClicked シグナルを発行 (MainWindow側で処理するように変更)
            self.doubleClicked.emit(self)
        # 親クラスのイベント処理も呼び出す
        super().mouseDoubleClickEvent(event)

    def get_main_window(self):
        """親ウィジェットを辿って MainWindow インスタンスを取得"""
        parent = self.parent()
        while parent is not None:
            # MainWindow クラスのインスタンスか、特定のメソッドを持っているかで判断
            # ここでは action_handler を持っているかで判断 (より確実)
            if hasattr(parent, "action_handler"):
                return parent
            parent = parent.parent()
        return None # 見つからなかった場合
