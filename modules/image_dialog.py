# modules/image_dialog.py
import json
import os
import re
import logging
from typing import List, Dict, Optional, Tuple, Set, Any, Union # Union をインポート
from PyQt6.QtWidgets import (
    QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QTextBrowser,
    QApplication, QScrollArea, QTabWidget, QTextEdit, QWidget, QSizePolicy
)
# QFont は削除 (フォント指定なしに戻すため)
from PyQt6.QtGui import QPixmap, QTextCursor, QTextCharFormat, QColor, QMouseEvent, QWheelEvent, QKeyEvent, QPainter
from PyQt6.QtCore import Qt, QPoint, pyqtSignal, QEvent, QSize, QRect, QObject
from .constants import ( # 定数をインポート
    # MetadataKeys はここでは使用しない (元のキー名に戻すため)
    PREVIEW_MODE_SEAMLESS, PREVIEW_MODE_WHEEL,
    METADATA_DIALOG_MIN_WIDTH, METADATA_DIALOG_MIN_HEIGHT,
    IMAGE_DIALOG_MIN_WIDTH, IMAGE_DIALOG_MIN_HEIGHT
)

logger = logging.getLogger(__name__)

# --- TagTextBrowser ---
# (リファクタリング後の正規表現版を維持します)
class TagTextBrowser(QTextBrowser):
    """
    テキスト内のタグを解析し、クリックやドラッグで選択・ハイライトできる
    カスタム QTextBrowser。
    タグはカンマ区切り、<...>, (...), \(...\) 形式に対応。
    """
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setOpenExternalLinks(False)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)

        self.selected_tags: Set[str] = set()
        self.tag_positions: List[Tuple[int, int, str]] = []
        self.drag_start_pos: Optional[int] = None

        self.viewport().setMouseTracking(True)
        self.viewport().installEventFilter(self)
        # フォント指定は削除

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            scroll_pos = self.verticalScrollBar().value()
            cursor = self.cursorForPosition(event.pos())
            position = cursor.position()
            self.drag_start_pos = position

            tag_clicked = False
            for start, end, tag_text in self.tag_positions:
                if start <= position < end:
                    logger.debug(f"Tag clicked: '{tag_text}'")
                    if tag_text in self.selected_tags:
                        self.selected_tags.remove(tag_text)
                    else:
                        self.selected_tags.add(tag_text)
                    self.update_highlight()
                    tag_clicked = True
                    break

            if not tag_clicked:
                 super().mousePressEvent(event)

            self.verticalScrollBar().setValue(scroll_pos)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton and self.drag_start_pos is not None:
            scroll_pos = self.verticalScrollBar().value()
            cursor = self.cursorForPosition(event.pos())
            current_pos = cursor.position()

            start_pos = min(self.drag_start_pos, current_pos)
            end_pos = max(self.drag_start_pos, current_pos)

            new_selected_tags = set()
            for tag_start, tag_end, tag_text in self.tag_positions:
                if max(tag_start, start_pos) < min(tag_end, end_pos):
                    new_selected_tags.add(tag_text)

            if new_selected_tags != self.selected_tags:
                 self.selected_tags = new_selected_tags
                 self.update_highlight()

            self.verticalScrollBar().setValue(scroll_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = None
            super().mouseReleaseEvent(event)
        else:
            super().mouseReleaseEvent(event)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj == self.viewport():
            pass
        return super().eventFilter(obj, event)

    def clear_selection(self) -> None:
        if self.selected_tags:
             self.selected_tags.clear()
             self.update_highlight()
             logger.debug("Tag selection cleared.")

    def update_highlight(self) -> None:
        logger.debug(f"Updating highlight. Selected tags: {self.selected_tags}")
        current_cursor = self.textCursor()
        saved_selection_start = current_cursor.selectionStart()
        saved_selection_end = current_cursor.selectionEnd()
        saved_position = current_cursor.position()

        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        default_format = QTextCharFormat()
        cursor.setCharFormat(default_format)
        cursor.clearSelection()

        highlight_format = QTextCharFormat()
        highlight_format.setBackground(QColor(255, 165, 0))

        for start, end, tag_text in self.tag_positions:
            if tag_text in self.selected_tags:
                cursor.setPosition(start)
                cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
                cursor.setCharFormat(highlight_format)
                cursor.clearSelection()

        final_cursor = self.textCursor()
        if saved_selection_start != saved_selection_end:
             final_cursor.setPosition(saved_selection_start)
             final_cursor.setPosition(saved_selection_end, QTextCursor.MoveMode.KeepAnchor)
        else:
             final_cursor.setPosition(saved_position)
        self.setTextCursor(final_cursor)

    def parse_and_set_text(self, text: str) -> None:
        """
        与えられたテキストを解析してタグを検出し、表示を更新します。
        タグは正規表現を用いて検出されます。カンマ区切り、<...>, (...), \(...\) 形式に対応。
        スペースはタグの区切り文字として扱いません。
        """
        self.clear() # 既存のテキストと状態をクリア
        self.selected_tags = set()
        self.tag_positions = []

        if not text:
            self.setPlainText("")
            return

        self.setPlainText(text) # まず全文を表示

        cursor = 0
        text_len = len(text)
        detected_tags_info = [] # デバッグ用

        while cursor < text_len:
            # 先行する空白やカンマをスキップ
            match_space_comma = re.match(r'[\s,]+', text[cursor:])
            if match_space_comma:
                cursor += match_space_comma.end()
                continue

            # ループ終了条件のチェック (スキップ後に再度チェック)
            if cursor >= text_len:
                break

            matched = False
            # 優先度順にタグパターンを試す
            patterns = [
                # 1. エスケープされた丸括弧 (Non-greedy)
                (r'\\\([^)]*?\\\)', 'escaped_paren'),
                # 2. 角括弧 (Non-greedy)
                (r'<[^>]*?>', 'bracket'),
                # 3. 丸括弧 (Non-greedy, ネスト非対応)
                (r'\([^)]*?\)', 'paren'),
                # ★★★ 通常タグのパターン修正: `\s` (スペース) を区切り文字から除外 ★★★
                (r'(?:\\.|[^,<()])+', 'normal') # カンマと括弧のみを区切り文字とする
            ]

            for pattern, tag_type in patterns:
                match = re.match(pattern, text[cursor:])
                if match:
                    tag_text = match.group(0)
                    start = cursor
                    end = cursor + match.end()

                    # マッチしたタグ文字列の前後の空白を除去してタグとする
                    cleaned_tag_text = tag_text.strip()

                    if cleaned_tag_text: # 空でなければタグとして記録
                        self.tag_positions.append((start, end, cleaned_tag_text))
                        detected_tags_info.append(f"'{cleaned_tag_text}' ({tag_type}) at {start}-{end}")

                    cursor = end # カーソルを進める
                    matched = True
                    break # マッチしたら次の位置へ

            if not matched:
                # どのパターンにもマッチしない場合 (予期せぬ文字など)、1文字進める
                logger.warning(f"Tag parsing: Unmatched character at index {cursor}: '{text[cursor]}'")
                cursor += 1

        logger.debug("Tag parsing complete.")
        # for info in detected_tags_info: logger.debug(f"  {info}")

    def get_selected_tags(self) -> List[str]:
        ordered_selected_tags = []
        for start, end, tag_text in self.tag_positions:
            if tag_text in self.selected_tags:
                ordered_selected_tags.append(tag_text)
        return ordered_selected_tags

# --- MetadataDialog (リファクタリング前に戻す部分) ---
class MetadataDialog(QDialog):
    """
    画像のメタデータ（Positive/Negative/Other）を表示するダイアログ。
    JSON文字列を受け取り、内部でパースして表示します。
    """
    def __init__(self, metadata_json: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Metadata")
        self.metadata_dict: Dict[str, Any] = {}
        self._parse_metadata_json(metadata_json)

        self.tab_widget: Optional[QTabWidget] = None
        self.metadata_tab: Optional[QWidget] = None
        self.select_tab: Optional[QWidget] = None
        self.metadata_positive_edit: Optional[QTextEdit] = None
        self.metadata_negative_edit: Optional[QTextEdit] = None
        self.metadata_others_edit: Optional[QTextEdit] = None
        self.select_positive_browser: Optional[TagTextBrowser] = None
        self.select_negative_browser: Optional[TagTextBrowser] = None
        self.select_others_browser: Optional[TagTextBrowser] = None
        self.clipboard_button: Optional[QPushButton] = None
        self.clear_button: Optional[QPushButton] = None

        self.initUI()
        self.setMinimumSize(METADATA_DIALOG_MIN_WIDTH, METADATA_DIALOG_MIN_HEIGHT)

    def _parse_metadata_json(self, metadata_json: str) -> None:
        """内部のメタデータ辞書をJSON文字列から更新します。"""
        try:
            self.metadata_dict = json.loads(metadata_json)
        except json.JSONDecodeError as e:
            logger.error(f"メタデータのJSONデコードに失敗しました: {e}", exc_info=True)
            self.metadata_dict = {
                "error": f"Invalid JSON format: {e}",
                "raw_data": metadata_json
            }
        except Exception as e:
             logger.error(f"メタデータの処理中に予期せぬエラー: {e}", exc_info=True)
             self.metadata_dict = {"error": f"Error processing metadata: {e}"}

    def initUI(self) -> None:
        """ダイアログのUIを初期化します。"""
        layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget(self)

        self.metadata_tab = QWidget()
        self._setup_metadata_tab()
        self.tab_widget.addTab(self.metadata_tab, "Metadata (Select Text)")

        self.select_tab = QWidget()
        self._setup_select_tab()
        self.tab_widget.addTab(self.select_tab, "Select (Select Tags)")

        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tab_widget)

        button_layout = QHBoxLayout()
        self.clipboard_button = QPushButton("Copy Selected to Clipboard")
        self.clipboard_button.clicked.connect(self.copy_to_clipboard)
        button_layout.addStretch()
        button_layout.addWidget(self.clipboard_button)

        self.clear_button = QPushButton("Clear Selection")
        self.clear_button.clicked.connect(self.clear_all_selections)
        button_layout.addWidget(self.clear_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        self.tab_widget.setCurrentIndex(0)
        self._update_button_state()

    def _setup_metadata_tab(self) -> None:
        """Metadataタブ（通常のテキスト表示）のUIをセットアップします。"""
        layout = QVBoxLayout(self.metadata_tab)
        self.metadata_positive_edit = self._create_metadata_text_edit(
            self.metadata_dict.get("positive_prompt", "N/A")
        )
        self.metadata_negative_edit = self._create_metadata_text_edit(
            self.metadata_dict.get("negative_prompt", "N/A")
        )
        self.metadata_others_edit = self._create_metadata_text_edit(
            self.metadata_dict.get("generation_info", "N/A")
        )
        layout.addWidget(QLabel("Positive Prompt:"))
        layout.addWidget(self.metadata_positive_edit)
        layout.addWidget(QLabel("Negative Prompt:"))
        layout.addWidget(self.metadata_negative_edit)
        layout.addWidget(QLabel("Other Generation Info:"))
        layout.addWidget(self.metadata_others_edit)

    def _create_metadata_text_edit(self, content: str) -> QTextEdit:
        """読み取り専用のQTextEditを作成し、設定します。"""
        text_edit = QTextEdit(self)
        # フォント指定は削除
        text_edit.setPlainText(content)
        text_edit.setReadOnly(True)
        text_edit.selectionChanged.connect(
            lambda: self._handle_selection_change(text_edit, self.metadata_positive_edit, self.metadata_negative_edit, self.metadata_others_edit)
        )
        return text_edit

    def _setup_select_tab(self) -> None:
        """Selectタブ（タグ選択機能）のUIをセットアップします。"""
        layout = QVBoxLayout(self.select_tab)
        self.select_positive_browser = self._create_tag_browser(
            self.metadata_dict.get("positive_prompt", "N/A")
        )
        self.select_negative_browser = self._create_tag_browser(
            self.metadata_dict.get("negative_prompt", "N/A")
        )
        self.select_others_browser = self._create_tag_browser(
            self.metadata_dict.get("generation_info", "N/A")
        )
        layout.addWidget(QLabel("Positive Prompt (Click or Drag Tags):"))
        layout.addWidget(self.select_positive_browser)
        layout.addWidget(QLabel("Negative Prompt (Click or Drag Tags):"))
        layout.addWidget(self.select_negative_browser)
        layout.addWidget(QLabel("Other Generation Info (Click or Drag Tags):"))
        layout.addWidget(self.select_others_browser)

    def _create_tag_browser(self, content: str) -> TagTextBrowser:
        """TagTextBrowserを作成し、設定します。"""
        browser = TagTextBrowser(self)
        # フォント指定は削除
        browser.parse_and_set_text(content)
        browser.mousePressEvent = lambda event, b=browser: self._handle_tag_browser_press(event, b)
        browser.mouseReleaseEvent = lambda event, b=browser: self._handle_tag_browser_release(event, b)
        return browser

    def _handle_selection_change(self, current_edit: QTextEdit, *other_edits: QTextEdit) -> None:
        """QTextEditの選択状態が変わったときの処理。"""
        if current_edit.textCursor().hasSelection():
            for other_edit in other_edits:
                # None チェックを追加
                if other_edit and other_edit != current_edit and other_edit.textCursor().hasSelection():
                    cursor = other_edit.textCursor()
                    cursor.clearSelection()
                    other_edit.setTextCursor(cursor)
        self._update_button_state()

    def _handle_tag_browser_press(self, event: QMouseEvent, current_browser: TagTextBrowser) -> None:
        """TagTextBrowserがクリックされたときの処理。"""
        browsers = [self.select_positive_browser, self.select_negative_browser, self.select_others_browser]
        for browser in browsers:
            if browser and browser != current_browser: # None チェックを追加
                browser.clear_selection()
        TagTextBrowser.mousePressEvent(current_browser, event)
        self._update_button_state()

    def _handle_tag_browser_release(self, event: QMouseEvent, current_browser: TagTextBrowser) -> None:
        """TagTextBrowserのマウスボタンが離されたときの処理。"""
        TagTextBrowser.mouseReleaseEvent(current_browser, event)
        self._update_button_state()

    def _on_tab_changed(self, index: int) -> None:
        """タブが切り替わったときに選択状態をクリアし、ボタン状態を更新します。"""
        logger.debug(f"Tab changed to index: {index}")
        if self.clipboard_button and self.clear_button:
            self.clear_all_selections()
            self._update_button_state()
        else:
            logger.warning("_on_tab_changed called before buttons were initialized.")

    def _update_button_state(self) -> None:
        """現在の選択状態に基づいてボタンの有効/無効を切り替えます。"""
        if not self.clipboard_button or not self.clear_button:
            logger.debug("_update_button_state skipped: buttons not initialized yet.")
            return

        has_selection = False
        if self.tab_widget:
             current_tab_index = self.tab_widget.currentIndex()
             if current_tab_index == 0:
                 if (self.metadata_positive_edit and self.metadata_positive_edit.textCursor().hasSelection()) or \
                    (self.metadata_negative_edit and self.metadata_negative_edit.textCursor().hasSelection()) or \
                    (self.metadata_others_edit and self.metadata_others_edit.textCursor().hasSelection()):
                     has_selection = True
             elif current_tab_index == 1:
                 if (self.select_positive_browser and self.select_positive_browser.selected_tags) or \
                    (self.select_negative_browser and self.select_negative_browser.selected_tags) or \
                    (self.select_others_browser and self.select_others_browser.selected_tags):
                     has_selection = True

        self.clipboard_button.setEnabled(has_selection)
        self.clear_button.setEnabled(has_selection)

    def copy_to_clipboard(self) -> None:
        """選択されたテキストまたはタグをクリップボードにコピーします。"""
        selected_text = ""
        current_tab_index = self.tab_widget.currentIndex() if self.tab_widget else -1

        if current_tab_index == 0:
            edits = [self.metadata_positive_edit, self.metadata_negative_edit, self.metadata_others_edit]
            for text_edit in edits:
                if text_edit and text_edit.textCursor().hasSelection():
                    selected_text = text_edit.textCursor().selectedText()
                    break
        elif current_tab_index == 1:
            tags_to_copy = []
            browsers = [self.select_positive_browser, self.select_negative_browser, self.select_others_browser]
            for browser in browsers:
                 if browser:
                      selected_tags = browser.get_selected_tags()
                      if selected_tags:
                           tags_to_copy = selected_tags
                           break
            if tags_to_copy:
                 selected_text = ", ".join(tags_to_copy)

        if selected_text:
            clipboard = QApplication.clipboard()
            clipboard.setText(selected_text)
            logger.info(f"クリップボードにコピーしました: '{selected_text[:50]}...'")
        else:
            logger.warning("コピーするテキストが選択されていません。")
        self._update_button_state()

    def clear_all_selections(self) -> None:
        """現在のタブに応じて選択を解除します。"""
        current_tab_index = self.tab_widget.currentIndex() if self.tab_widget else -1
        logger.debug(f"Clearing selection for tab index: {current_tab_index}")

        if current_tab_index == 0:
            edits = [self.metadata_positive_edit, self.metadata_negative_edit, self.metadata_others_edit]
            for text_edit in edits:
                if text_edit and text_edit.textCursor().hasSelection():
                    cursor = text_edit.textCursor()
                    cursor.clearSelection()
                    text_edit.setTextCursor(cursor)
        elif current_tab_index == 1:
            browsers = [self.select_positive_browser, self.select_negative_browser, self.select_others_browser]
            for browser in browsers:
                if browser:
                    browser.clear_selection()
        self._update_button_state()

    def update_metadata(self, metadata_json: str) -> None:
        """
        表示するメタデータをJSON文字列から更新します。
        """
        logger.info("メタデータを更新します。")
        self._parse_metadata_json(metadata_json)
        try:
            # None チェックを追加
            if self.metadata_positive_edit:
                 self.metadata_positive_edit.setPlainText(self.metadata_dict.get("positive_prompt", "N/A"))
            if self.metadata_negative_edit:
                 self.metadata_negative_edit.setPlainText(self.metadata_dict.get("negative_prompt", "N/A"))
            if self.metadata_others_edit:
                 self.metadata_others_edit.setPlainText(self.metadata_dict.get("generation_info", "N/A"))

            if self.select_positive_browser:
                 self.select_positive_browser.parse_and_set_text(self.metadata_dict.get("positive_prompt", "N/A"))
            if self.select_negative_browser:
                 self.select_negative_browser.parse_and_set_text(self.metadata_dict.get("negative_prompt", "N/A"))
            if self.select_others_browser:
                 self.select_others_browser.parse_and_set_text(self.metadata_dict.get("generation_info", "N/A"))

            self.clear_all_selections()
        except Exception as e:
            logger.error(f"メタデータUIの更新中にエラーが発生しました: {e}", exc_info=True)

# --- ImageDialog (リファクタリング後の状態を維持) ---
class ImageDialog(QDialog):
    # ... (前回の ImageDialog のコードをそのまま記述) ...
    # (長いので省略しますが、前回のメッセージの ImageDialog クラスの内容です)
    def __init__(self,
                 all_image_paths: List[str],
                 current_index: int,
                 preview_mode: str = PREVIEW_MODE_SEAMLESS,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Image Preview")

        if not all_image_paths or not (0 <= current_index < len(all_image_paths)):
             logger.error("ImageDialog に無効な画像リストまたはインデックスが渡されました。")
             all_image_paths = []
             current_index = -1

        self.all_image_paths: List[str] = all_image_paths
        self.current_index: int = current_index
        self.preview_mode: str = preview_mode
        self.pixmap: Optional[QPixmap] = None
        self.scale_factor: float = 1.0
        self.drag_start_pos: Optional[QPoint] = None
        self.scroll_start_h: int = 0
        self.scroll_start_v: int = 0
        self.is_maximized: bool = False
        self.saved_geometry: Optional[bytes] = None

        self.image_label: Optional[QLabel] = None
        self.scroll_area: Optional[QScrollArea] = None
        self.prev_button: Optional[QPushButton] = None
        self.next_button: Optional[QPushButton] = None
        self.counter_label: Optional[QLabel] = None
        self.maximize_button: Optional[QPushButton] = None

        self._setup_ui()
        self.setMinimumSize(IMAGE_DIALOG_MIN_WIDTH, IMAGE_DIALOG_MIN_HEIGHT)
        self.resize(1000, 800)

        if self.current_index != -1:
             self._load_image(self.all_image_paths[self.current_index])

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        toolbar_layout = self._create_toolbar()
        main_layout.addLayout(toolbar_layout)
        image_area_widget = self._create_image_area()
        main_layout.addWidget(image_area_widget, 1)
        self.setLayout(main_layout)

    def _create_toolbar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.prev_button = QPushButton("← Previous")
        self.prev_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.prev_button.clicked.connect(self.show_previous_image)
        self.counter_label = QLabel("0 / 0")
        self.counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.counter_label.setMinimumWidth(80)
        self.next_button = QPushButton("Next →")
        self.next_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.next_button.clicked.connect(self.show_next_image)
        self.maximize_button = QPushButton("□")
        self.maximize_button.setFixedSize(30, 30)
        self.maximize_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.maximize_button.setToolTip("Maximize/Restore Window")
        self.maximize_button.clicked.connect(self.toggle_maximize)
        layout.addWidget(self.prev_button)
        layout.addStretch()
        layout.addWidget(self.counter_label)
        layout.addStretch()
        layout.addWidget(self.next_button)
        layout.addSpacing(20)
        layout.addWidget(self.maximize_button)
        return layout

    def _create_image_area(self) -> QWidget:
        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: black;")
        if self.preview_mode == PREVIEW_MODE_SEAMLESS:
             logger.info("Seamless preview mode selected.")
             self.image_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
             return self.image_label
        elif self.preview_mode == PREVIEW_MODE_WHEEL:
             logger.info("Wheel preview mode selected.")
             self.scroll_area = QScrollArea(self)
             self.scroll_area.setWidgetResizable(True)
             self.scroll_area.setWidget(self.image_label)
             self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
             self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
             self.scroll_area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
             self.setToolTip("Ctrl + Wheel to zoom, Drag to pan")
             return self.scroll_area
        else:
             logger.warning(f"Unknown preview mode: {self.preview_mode}. Falling back to seamless.")
             self.preview_mode = PREVIEW_MODE_SEAMLESS
             return self.image_label

    def _load_image(self, image_path: str) -> None:
        logger.info(f"Loading image: {image_path}")
        self.image_path = image_path
        try:
            self.pixmap = QPixmap(image_path)
            if self.pixmap.isNull():
                 logger.error(f"Failed to load image (Pixmap is null): {image_path}")
                 self.image_label.setText(f"Error loading:\n{os.path.basename(image_path)}")
                 self.pixmap = None
                 return
            self.setWindowTitle(f"Image Preview - {os.path.basename(image_path)}")
            self.scale_factor = 1.0
            self._update_image_display()
            self._update_navigation()
        except Exception as e:
            logger.error(f"Error loading image {image_path}: {e}", exc_info=True)
            self.image_label.setText(f"Error:\n{e}")
            self.pixmap = None

    def _update_image_display(self) -> None:
        if not self.pixmap or self.image_label is None:
             logger.debug("_update_image_display skipped: no pixmap or label.")
             return
        if self.preview_mode == PREVIEW_MODE_SEAMLESS:
            target_size = self.image_label.size()
            scaled_pixmap = self.pixmap.scaled(target_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.image_label.setPixmap(scaled_pixmap)
            logger.debug(f"Seamless mode: Pixmap updated and scaled to fit {target_size}.")
        elif self.preview_mode == PREVIEW_MODE_WHEEL:
            scaled_size = self.pixmap.size() * self.scale_factor
            scaled_pixmap = self.pixmap.scaled(scaled_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.image_label.setPixmap(scaled_pixmap)
            self.image_label.resize(scaled_pixmap.size())
            logger.debug(f"Wheel mode: Pixmap updated with scale factor {self.scale_factor:.2f}. Size: {scaled_pixmap.size()}")

    def _update_navigation(self) -> None:
        total_images = len(self.all_image_paths)
        has_prev = self.current_index > 0
        has_next = self.current_index < total_images - 1
        if self.prev_button: self.prev_button.setEnabled(has_prev)
        if self.next_button: self.next_button.setEnabled(has_next)
        if self.counter_label:
            if total_images > 0:
                 self.counter_label.setText(f"{self.current_index + 1} / {total_images}")
            else:
                 self.counter_label.setText("0 / 0")

    def show_next_image(self) -> None:
        if self.current_index < len(self.all_image_paths) - 1:
            self.current_index += 1
            self._load_image(self.all_image_paths[self.current_index])
        else:
             logger.debug("Already at the last image.")

    def show_previous_image(self) -> None:
        if self.current_index > 0:
            self.current_index -= 1
            self._load_image(self.all_image_paths[self.current_index])
        else:
             logger.debug("Already at the first image.")

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.preview_mode == PREVIEW_MODE_WHEEL:
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                angle = event.angleDelta().y()
                if angle > 0: self.scale_factor *= 1.15
                elif angle < 0: self.scale_factor /= 1.15
                min_scale = 0.1
                self.scale_factor = max(min_scale, self.scale_factor)
                logger.debug(f"Zooming with Ctrl+Wheel. New scale factor: {self.scale_factor:.2f}")
                self._update_image_display()
                event.accept()
            else:
                 if self.scroll_area:
                      delta = event.angleDelta().y()
                      self.scroll_area.verticalScrollBar().setValue(
                           self.scroll_area.verticalScrollBar().value() - delta
                      )
                      event.accept()
        else: pass

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Right or key == Qt.Key.Key_Space: self.show_next_image()
        elif key == Qt.Key.Key_Left or key == Qt.Key.Key_Backspace: self.show_previous_image()
        elif key == Qt.Key.Key_Escape: self.close()
        elif key == Qt.Key.Key_F: self.toggle_maximize()
        else: super().keyPressEvent(event)
        event.accept() # ここで accept するか、各分岐で accept するか

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.preview_mode == PREVIEW_MODE_WHEEL and self.scroll_area:
            if (self.image_label.width() > self.scroll_area.width() or
                self.image_label.height() > self.scroll_area.height()):
                 if event.button() == Qt.MouseButton.LeftButton:
                      self.drag_start_pos = event.pos()
                      self.scroll_start_v = self.scroll_area.verticalScrollBar().value()
                      self.scroll_start_h = self.scroll_area.horizontalScrollBar().value()
                      self.image_label.setCursor(Qt.CursorShape.ClosedHandCursor)
                      event.accept()
                 else: super().mousePressEvent(event)
            else: super().mousePressEvent(event)
        else: super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.preview_mode == PREVIEW_MODE_WHEEL and self.drag_start_pos and self.scroll_area:
            if event.buttons() & Qt.MouseButton.LeftButton:
                delta = event.pos() - self.drag_start_pos
                self.scroll_area.verticalScrollBar().setValue(self.scroll_start_v - delta.y())
                self.scroll_area.horizontalScrollBar().setValue(self.scroll_start_h - delta.x())
                event.accept()
            else:
                 self.drag_start_pos = None
                 self.image_label.setCursor(Qt.CursorShape.ArrowCursor)
                 super().mouseMoveEvent(event)
        else: super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self.preview_mode == PREVIEW_MODE_WHEEL:
            if event.button() == Qt.MouseButton.LeftButton and self.drag_start_pos:
                self.drag_start_pos = None
                self.image_label.setCursor(Qt.CursorShape.ArrowCursor)
                event.accept()
            else: super().mouseReleaseEvent(event)
        else: super().mouseReleaseEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.preview_mode == PREVIEW_MODE_SEAMLESS:
            self._update_image_display()

    def toggle_maximize(self) -> None:
        if not self.is_maximized:
            logger.info("Maximizing window.")
            self.saved_geometry = self.saveGeometry()
            self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)
            self.is_maximized = True
            self.maximize_button.setText("❐")
            self.maximize_button.setToolTip("Restore Window")
        else:
            logger.info("Restoring window from maximized state.")
            self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMaximized)
            if self.saved_geometry:
                 if self.restoreGeometry(self.saved_geometry): logger.debug("Geometry restored successfully.")
                 else: logger.warning("Failed to restore geometry.")
                 self.saved_geometry = None
            self.is_maximized = False
            self.maximize_button.setText("□")
            self.maximize_button.setToolTip("Maximize Window")
        self._update_image_display()

# --- 実行ブロック (テスト用) ---
if __name__ == "__main__":
    app = QApplication([])
    print("Testing MetadataDialog...")
    test_metadata_json = json.dumps({ # JSON文字列として渡す
        "positive_prompt": "masterpiece, best quality, 1girl, solo, <lora:char:1>, (detailed background:1.2), smile",
        "negative_prompt": "(worst quality, low quality:1.4), bad anatomy, blurry, deformed, missing fingers",
        "generation_info": "Steps: 30, Sampler: DPM++ 2M Karras, CFG scale: 7, Seed: 12345, Size: 512x768, Model hash: abcdef1234, Clip skip: 2, ENSD: 31337"
    })
    metadata_dialog = MetadataDialog(test_metadata_json)
    metadata_dialog.show()

    dummy_image_paths = ["dummy_image_1.png", "dummy_image_2.jpg"]
    if dummy_image_paths and os.path.exists(dummy_image_paths[0]):
        print("\nTesting ImageDialog (Wheel Mode)...")
        image_dialog_wheel = ImageDialog(dummy_image_paths, 0, PREVIEW_MODE_WHEEL)
        image_dialog_wheel.show()
    else:
        print(f"\nSkipping ImageDialog test: Image(s) not found.")

    sys.exit(app.exec())