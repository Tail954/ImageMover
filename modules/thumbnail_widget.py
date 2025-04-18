# modules/thumbnail_widget.py
import os
import logging
from typing import Optional
from PyQt6.QtWidgets import QLabel, QWidget
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QMouseEvent
# from modules.metadata import extract_metadata # ここでの直接使用は不要になった
from .thumbnail_cache import ThumbnailCache
from .constants import DEFAULT_THUMBNAIL_SIZE, THUMBNAIL_BORDER_SELECTED, THUMBNAIL_ORDER_LABEL_STYLE
# ImageDialog のインポートを先頭に移動 (mouseDoubleClickEvent で使用するため)
from .image_dialog import ImageDialog

logger = logging.getLogger(__name__)

class ImageThumbnail(QLabel):
    """
    グリッド表示用の画像サムネイルウィジェット。
    クリック、右クリック、ダブルクリックイベントをシグナルとして発行し、
    親ウィジェット (MainWindow) と疎結合に連携します。
    """
    # --- シグナル定義 ---
    # 左クリックされたときに発行。引数は新しい選択状態 (True:選択, False:解除)
    clicked = pyqtSignal(bool)
    # 右クリックされたときに発行
    rightClicked = pyqtSignal()
    # ダブルクリックされたときに発行
    doubleClicked = pyqtSignal()

    def __init__(self, image_path: str,
                 thumbnail_cache: ThumbnailCache,
                 parent: Optional[QWidget] = None):
        """
        ImageThumbnailを初期化します。

        Args:
            image_path: 表示する画像のパス。
            thumbnail_cache: 使用するThumbnailCacheのインスタンス。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self.image_path: str = image_path
        self._thumbnail_cache: ThumbnailCache = thumbnail_cache
        self._selected: bool = False
        self._order: int = -1 # コピーモード時の選択順序

        self.setFixedSize(DEFAULT_THUMBNAIL_SIZE, DEFAULT_THUMBNAIL_SIZE)
        # setScaledContents(True) にすると、画像が QLabel のサイズに合わせて拡縮される
        # KeepAspectRatio を維持しつつ中央揃えにするには、スタイルシートや手動での描画が必要になる場合がある
        # 今回は Cache で適切なサイズの Pixmap を作っているので False のままでも良い
        self.setScaledContents(False)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter) # 画像を中央揃えに

        self._load_thumbnail()

        # ツールチップに親フォルダ名を表示（既存の動作）
        try:
             parent_dir = os.path.dirname(image_path)
             self.setToolTip(parent_dir)
        except Exception as e:
             logger.warning(f"ツールチップ設定中にエラー: {e}", exc_info=False)
             self.setToolTip(image_path) # フォールバックとしてフルパス

        # コピーモード時の順序表示用ラベル
        self._order_label = QLabel(self)
        self._order_label.setStyleSheet(THUMBNAIL_ORDER_LABEL_STYLE)
        self._order_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 左上に配置（サイズは適宜調整）
        self._order_label.setGeometry(0, 0, 25, 25)
        self._order_label.hide() # 初期状態では非表示

    def _load_thumbnail(self) -> None:
        """サムネイルをキャッシュから読み込み、表示します。"""
        try:
            pixmap = self._thumbnail_cache.get_thumbnail(self.image_path, DEFAULT_THUMBNAIL_SIZE)
            if pixmap:
                # QLabel のサイズに合わせて Pixmap をスケーリングして設定
                # scaled() はアスペクト比を保つ
                scaled_pixmap = pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.setPixmap(scaled_pixmap)
            else:
                logger.warning(f"サムネイルの取得に失敗しました: {self.image_path}")
                self.setText("Load Err") # エラー表示
                self.setStyleSheet("color: red;") # エラー時は赤文字
        except Exception as e:
            logger.error(f"サムネイル読み込み中に予期せぬエラー ({self.image_path}): {e}", exc_info=True)
            self.setText("Error")
            self.setStyleSheet("color: red;")

    # --- Public Methods for State Update (Called by MainWindow) ---

    def set_selected_visuals(self, selected: bool) -> None:
        """
        選択状態に基づいて視覚的な表示（ボーダー）を更新します。
        このメソッドは通常、MainWindow から呼び出されます。

        Args:
            selected: 新しい選択状態。
        """
        self._selected = selected
        if self._selected:
            self.setStyleSheet(THUMBNAIL_BORDER_SELECTED)
        else:
            # エラー表示でない場合のみスタイルをクリア
            if self.text() == "": # pixmapが表示されている場合
                 self.setStyleSheet("")
        # logger.debug(f"Set selected visuals for {os.path.basename(self.image_path)}: {selected}")


    def set_order_label(self, order: Optional[int]) -> None:
        """
        コピーモード時の選択順序ラベルを表示または非表示にします。
        このメソッドは通常、MainWindow から呼び出されます。

        Args:
            order: 表示する順序番号。None または 0 以下の場合は非表示。
        """
        if order is not None and order > 0:
            self._order = order
            self._order_label.setText(str(order))
            self._order_label.show()
            # logger.debug(f"Set order label for {os.path.basename(self.image_path)}: {order}")
        else:
            self._order = -1
            self._order_label.hide()
            # logger.debug(f"Hide order label for {os.path.basename(self.image_path)}")

    # --- Event Handlers ---

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """マウスボタンが押されたときのイベントハンドラ。"""
        if event.button() == Qt.MouseButton.LeftButton:
            # 左クリック：選択状態を反転し、clicked シグナルを発行
            new_selection_state = not self._selected
            logger.debug(f"Left click on {os.path.basename(self.image_path)}. New state: {new_selection_state}")
            # 自身の選択状態は保持せず、常にシグナルを発行する
            # 実際の状態管理と表示更新は MainWindow 側で行う
            self.clicked.emit(new_selection_state)
            event.accept() # イベントを消費

        elif event.button() == Qt.MouseButton.RightButton:
            # 右クリック：rightClicked シグナルを発行
            logger.debug(f"Right click on {os.path.basename(self.image_path)}")
            self.rightClicked.emit()
            event.accept() # イベントを消費

        else:
            # 他のボタンの場合はデフォルトの処理
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """マウスがダブルクリックされたときのイベントハンドラ。"""
        if event.button() == Qt.MouseButton.LeftButton:
            # 左ダブルクリック：doubleClicked シグナルを発行
            logger.debug(f"Double click on {os.path.basename(self.image_path)}")
            self.doubleClicked.emit()
            event.accept() # イベントを消費
        else:
            # 他のボタンの場合はデフォルトの処理
            super().mouseDoubleClickEvent(event)

    # --- Properties ---

    @property
    def selected(self) -> bool:
        """現在の選択状態を取得します。"""
        # 注意: この selected 状態は MainWindow 側で管理されるべきであり、
        # このウィジェット内部の状態は MainWindow からの指示で更新される。
        # 直接このプロパティに依存するロジックは MainWindow 側に持つべき。
        return self._selected

    # selected の setter は MainWindow から set_selected_visuals() 経由で更新されるため不要

    @property
    def order(self) -> int:
        """現在のコピーモード選択順序を取得します。"""
        return self._order

    # order の setter は MainWindow から set_order_label() 経由で更新されるため不要