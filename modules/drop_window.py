# modules/drop_window.py
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QApplication
)
from PyQt6.QtCore import Qt, QUrl, QMimeData, QTimer
from PyQt6.QtGui import QScreen, QDragEnterEvent, QDropEvent, QDragMoveEvent

# 対応する画像ファイルの拡張子リスト (必要に応じて追加・修正してください)
IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp', '.heic', '.heif']

class DropWindow(QWidget):
    """
    画像ファイルのドラッグ＆ドロップを受け付け、メタデータを表示するウィンドウ。
    """
    def __init__(self, main_window):
        """
        コンストラクタ

        Args:
            main_window (MainWindow): メインウィンドウのインスタンス参照
        """
        super().__init__()
        self.main_window = main_window # MainWindow の参照を保持
        self.initUI()
        self.setAcceptDrops(True) # ドラッグアンドドロップを有効化

    def initUI(self):
        """UIの初期化"""
        self.setWindowTitle("D&D Metadata")
        # ウィンドウサイズを小さく固定
        self.setFixedSize(200, 150)

        # 常に最前面に表示し、ツールウィンドウスタイルにする（タスクバーに表示されにくい）
        # FramelessWindowHint はタイトルバーを消すが、移動できなくなるため注意
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool) # | Qt.WindowType.FramelessWindowHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10) # 内側のマージン

        self.label = QLabel("ここに画像ファイルを\nドロップしてください")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True) # テキストの折り返しを有効に
        layout.addWidget(self.label, 1) # ストレッチファクターでラベル領域を広げる

        self.close_button = QPushButton("閉じる")
        self.close_button.clicked.connect(self.close) # 閉じるボタンでウィンドウを閉じる
        layout.addWidget(self.close_button)

        self.setLayout(layout)

        # 画面右下に配置
        self.move_to_bottom_right()

    def move_to_bottom_right(self):
        """ウィンドウを画面の右下に移動する"""
        try:
            screen_geometry = QApplication.primaryScreen().availableGeometry()
            screen_width = screen_geometry.width()
            screen_height = screen_geometry.height()
            window_width = self.width()
            window_height = self.height()
            margin = 15 # 画面端からのマージン
            self.move(screen_width - window_width - margin, screen_height - window_height - margin)
        except Exception as e:
            print(f"画面右下への移動中にエラーが発生しました: {e}")


    def dragEnterEvent(self, event: QDragEnterEvent):
        """ファイルがウィンドウ上にドラッグされたときのイベント"""
        mime_data = event.mimeData()
        # ドラッグされたデータがURLリスト（ファイルパス）を持っているか確認
        if mime_data.hasUrls():
            # 最初のURLを取得
            url = mime_data.urls()[0]
            # ローカルファイルであり、かつ拡張子が画像のものかチェック
            if url.isLocalFile():
                file_path = url.toLocalFile()
                _, ext = os.path.splitext(file_path)
                if ext.lower() in IMAGE_EXTENSIONS:
                    event.acceptProposedAction() # ドロップ操作を受け入れる
                    self.label.setText("ドロップしてメタデータを表示...")
                    return # チェック成功
        event.ignore() # 受け入れない
        self.label.setText("ここに画像ファイルを\nドロップしてください") # ラベルを元に戻す

    def dragMoveEvent(self, event: QDragMoveEvent):
        """ファイルがウィンドウ上でドラッグ移動中のイベント"""
        # dragEnterEventでチェック済みなので、ここでは単純に受け入れる
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        """ドラッグがウィンドウから離れたときのイベント"""
        self.label.setText("ここに画像ファイルを\nドロップしてください")
        event.accept()

    def dropEvent(self, event: QDropEvent):
        """ファイルがウィンドウ上にドロップされたときのイベント"""
        mime_data = event.mimeData()
        original_text = "ここに画像ファイルを\nドロップしてください" # 元のテキスト

        if mime_data.hasUrls():
            url = mime_data.urls()[0] # 最初のファイルのみ処理
            if url.isLocalFile():
                file_path = url.toLocalFile()
                _, ext = os.path.splitext(file_path)
                if ext.lower() in IMAGE_EXTENSIONS:
                    print(f"画像ファイルがドロップされました: {file_path}")
                    try:
                        # MainWindow のメソッドを呼び出してメタデータダイアログを表示
                        self.main_window.show_metadata_dialog(file_path)
                        self.label.setText("メタデータを表示しました！")
                        event.acceptProposedAction()
                    except Exception as e:
                        print(f"メタデータ表示中にエラー: {e}")
                        self.label.setText("メタデータ表示に失敗しました。")
                        event.ignore()
                else:
                    self.label.setText("画像ファイルではありません。")
                    event.ignore()
            else:
                self.label.setText("ローカルファイルではありません。")
                event.ignore()
        else:
            self.label.setText("無効なデータです。")
            event.ignore()

        # ドロップ操作後、少し遅れてラベルを元のテキストに戻す
        QTimer.singleShot(2000, lambda: self.label.setText(original_text))

    def closeEvent(self, event):
        """ウィンドウが閉じられるときのイベント"""
        # MainWindow側の参照をクリアする
        if self.main_window:
            self.main_window.drop_window = None
        print("ドロップウィンドウを閉じました。")
        super().closeEvent(event)

