# modules/wc_creator.py
import os
import json
import logging
from typing import List, Dict, Optional, Tuple, Any
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QSplitter, QLabel,
    QTextEdit, QCheckBox, QScrollArea, QWidget, QLineEdit,
    QFileDialog, QApplication, QGridLayout, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from .thumbnail_cache import ThumbnailCache
from .metadata import extract_metadata # metadata モジュールをインポート
from .constants import ( # 定数をインポート
    MetadataKeys, OUTPUT_FORMAT_SEPARATE, OUTPUT_FORMAT_INLINE,
    PREVIEW_THUMBNAIL_SIZE, OUTPUT_PREVIEW_THUMBNAIL_SIZE,
    WC_CREATOR_DIALOG_WIDTH, WC_CREATOR_DIALOG_HEIGHT,
    OUTPUT_DIALOG_WIDTH, OUTPUT_DIALOG_HEIGHT
)

logger = logging.getLogger(__name__)

# --- Helper Function for Output Formatting ---

def _format_output_string(comment: str, prompt_lines: List[str], output_format: str) -> str:
    """
    コメントとプロンプト行を指定された形式で結合します。

    Args:
        comment: 追加するコメント文字列。
        prompt_lines: プロンプトの各行のリスト。
        output_format: 出力形式 ('separate_lines' または 'inline_format')。

    Returns:
        整形された出力文字列。
    """
    # プロンプト行をスペースで結合 (空行は除外されている前提)
    combined_prompt = " ".join(prompt_lines).strip()
    comment = comment.strip()

    if output_format == OUTPUT_FORMAT_SEPARATE:
        if comment and combined_prompt:
            return f"# {comment}\n{combined_prompt}"
        elif comment:
            return f"# {comment}"
        else: # combined_prompt のみ、または両方空
            return combined_prompt
    elif output_format == OUTPUT_FORMAT_INLINE:
        if comment and combined_prompt:
            return f"[{comment}:100]{combined_prompt}"
        else: # comment がない場合、または prompt がない場合
            return combined_prompt
    else:
        logger.warning(f"不明な出力フォーマット: {output_format}。デフォルト形式を使用します。")
        # フォールバックとして separate_lines 形式を使用
        if comment and combined_prompt:
            return f"# {comment}\n{combined_prompt}"
        elif comment:
            return f"# {comment}"
        else:
            return combined_prompt

# --- WCCreatorDialog ---

class WCCreatorDialog(QDialog):
    """
    選択された画像のPositive Promptを行ごとに表示し、
    選択・コメント追加・整形出力を行うダイアログ。
    """
    def __init__(self, selected_images: List[str],
                 thumbnail_cache: ThumbnailCache,
                 output_format: str = OUTPUT_FORMAT_SEPARATE,
                 parent: Optional[QWidget] = None):
        """
        WCCreatorDialogを初期化します。

        Args:
            selected_images: 処理対象の画像パスリスト。
            thumbnail_cache: サムネイルキャッシュ。
            output_format: 出力フォーマット。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self.setWindowTitle("WC Creator - Prompt Editor")
        self.setGeometry(150, 150, WC_CREATOR_DIALOG_WIDTH, WC_CREATOR_DIALOG_HEIGHT) # 位置調整

        if not selected_images:
            logger.warning("WCCreatorDialog: 選択された画像がありません。")
            # エラーメッセージを表示して早期リターンするなども考慮
            # QMessageBox.warning(self, "No Images", "No images selected for WC Creator.")
            # self.close() # or return

        self.selected_images: List[str] = selected_images
        self.thumbnail_cache: ThumbnailCache = thumbnail_cache
        self.output_format: str = output_format
        self.current_index: int = 0

        # 各画像のコメントとチェックボックス状態をキャッシュする辞書
        # key: 画像インデックス (int), value: コメント文字列 (str)
        self.comment_cache: Dict[int, str] = {}
        # key: 画像インデックス (int), value: チェック状態リスト ([bool])
        self.checkbox_state_cache: Dict[int, List[bool]] = {}

        # UI要素のプレースホルダー
        self.splitter: QSplitter = None
        self.left_panel: QWidget = None
        self.right_panel: QWidget = None
        self.image_label: QLabel = None
        self.prev_button: QPushButton = None
        self.next_button: QPushButton = None
        self.all_button: QPushButton = None
        self.comment_edit: QLineEdit = None
        self.scroll_area: QScrollArea = None
        self.scroll_content: QWidget = None
        self.prompt_layout: QVBoxLayout = None
        self.output_checked_button: QPushButton = None
        self.output_all_button: QPushButton = None
        self.clipboard_button: QPushButton = None
        self.prompt_checkboxes: List[QCheckBox] = [] # 現在表示中のチェックボックスリスト
        self.prompt_textboxes: List[QLineEdit] = [] # 現在表示中のテキストボックスリスト

        self.initUI()
        if self.selected_images:
             self._load_image_data(self.current_index)
        else:
             # 画像がない場合の初期表示処理
             self._update_navigation_buttons()
             self._clear_prompt_layout()
             logger.info("WCCreatorDialog: 画像がないため初期データロードをスキップしました。")


    def initUI(self) -> None:
        """ダイアログのUIを初期化します。"""
        main_layout = QHBoxLayout(self)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        self._setup_left_panel()
        self._setup_right_panel()

        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.right_panel)
        # 初期サイズ比率 (左:右 = 1:2)
        total_width = WC_CREATOR_DIALOG_WIDTH - 30 # マージン等を考慮
        self.splitter.setSizes([total_width // 3, total_width * 2 // 3])

        main_layout.addWidget(self.splitter)

    def _setup_left_panel(self) -> None:
        """左側のパネル（画像表示とナビゲーション）をセットアップします。"""
        self.left_panel = QWidget()
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)

        # サムネイル表示ラベル
        self.image_label = QLabel("No Image")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(PREVIEW_THUMBNAIL_SIZE, PREVIEW_THUMBNAIL_SIZE)
        self.image_label.setStyleSheet("border: 1px solid gray;") # 境界線
        left_layout.addWidget(self.image_label)

        # ナビゲーションボタン
        nav_layout = QHBoxLayout()
        self.prev_button = QPushButton("← Previous")
        self.prev_button.clicked.connect(self.show_previous_image)
        self.next_button = QPushButton("→ Next")
        self.next_button.clicked.connect(self.show_next_image)
        nav_layout.addWidget(self.prev_button)
        nav_layout.addStretch()
        nav_layout.addWidget(self.next_button)
        left_layout.addLayout(nav_layout)

    def _setup_right_panel(self) -> None:
        """右側のパネル（プロンプト編集と出力）をセットアップします。"""
        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(5, 5, 5, 5)

        # 上部コントロール (ALLボタン、コメント)
        top_layout = QHBoxLayout()
        self.all_button = QPushButton("ALL")
        self.all_button.setToolTip("Check/Uncheck All Prompt Lines")
        self.all_button.clicked.connect(self.toggle_all_checkboxes)
        self.comment_edit = QLineEdit()
        self.comment_edit.setPlaceholderText("Enter comment for this image")
        self.comment_edit.textChanged.connect(self._cache_current_comment) # 入力中にキャッシュ更新
        top_layout.addWidget(self.all_button)
        top_layout.addWidget(QLabel("Comment:"))
        top_layout.addWidget(self.comment_edit)
        right_layout.addLayout(top_layout)

        # プロンプト行表示用スクロールエリア
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.prompt_layout = QVBoxLayout(self.scroll_content)
        self.prompt_layout.setAlignment(Qt.AlignmentFlag.AlignTop) # 上詰め
        self.scroll_content.setLayout(self.prompt_layout)
        self.scroll_area.setWidget(self.scroll_content)
        right_layout.addWidget(self.scroll_area)

        # 下部ボタン (出力、クリップボード)
        bottom_layout = QHBoxLayout()
        self.output_checked_button = QPushButton("Output Checked")
        self.output_checked_button.clicked.connect(lambda: self.show_output_dialog(checked_only=True))
        self.output_all_button = QPushButton("Output All")
        self.output_all_button.clicked.connect(lambda: self.show_output_dialog(checked_only=False))
        self.clipboard_button = QPushButton("Copy Checked to Clipboard")
        self.clipboard_button.clicked.connect(self.copy_to_clipboard)

        bottom_layout.addWidget(self.output_checked_button)
        bottom_layout.addWidget(self.output_all_button)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.clipboard_button)
        right_layout.addLayout(bottom_layout)

    def _load_image_data(self, index: int) -> None:
        """
        指定されたインデックスの画像データをロードし、UIを更新します。
        移動前に現在の状態をキャッシュします。
        """
        if not self.selected_images or not (0 <= index < len(self.selected_images)):
            logger.warning(f"_load_image_data: 無効なインデックス {index}")
            return

        logger.info(f"Loading data for image index {index}")
        # 1. 移動前の状態をキャッシュ (現在のインデックスが有効な場合)
        self._cache_current_state()

        # 2. 新しいインデックスを設定し、UI要素を更新
        self.current_index = index
        current_image_path = self.selected_images[self.current_index]
        self._update_image_thumbnail(current_image_path)
        self._update_navigation_buttons()
        self._update_comment_field()

        # 3. プロンプト情報を読み込んで表示
        positive_prompt = self._get_positive_prompt(current_image_path)
        self._display_prompt_lines(positive_prompt)

        # 4. キャッシュされたチェック状態、または前の状態を適用
        self._apply_checkbox_state()

    def _cache_current_state(self) -> None:
        """現在のコメントとチェックボックスの状態をキャッシュします。"""
        # current_index が有効な範囲内であることを確認
        if 0 <= self.current_index < len(self.selected_images):
            # コメントのキャッシュ
             current_comment = self.comment_edit.text()
             self.comment_cache[self.current_index] = current_comment
             # logger.debug(f"Cached comment for index {self.current_index}: '{current_comment}'")

             # チェックボックス状態のキャッシュ
             if hasattr(self, 'prompt_checkboxes'):
                 current_checkbox_states = [cb.isChecked() for cb in self.prompt_checkboxes]
                 self.checkbox_state_cache[self.current_index] = current_checkbox_states
                 # logger.debug(f"Cached checkbox states for index {self.current_index}: {current_checkbox_states}")


    def _cache_current_comment(self) -> None:
        """コメントフィールドのテキストが変更されたときにキャッシュを更新します。"""
        if 0 <= self.current_index < len(self.selected_images):
             self.comment_cache[self.current_index] = self.comment_edit.text()


    def _update_image_thumbnail(self, image_path: str) -> None:
        """画像サムネイル表示を更新します。"""
        pixmap = self.thumbnail_cache.get_thumbnail(image_path, PREVIEW_THUMBNAIL_SIZE)
        if pixmap:
            # アスペクト比を保ってラベルにフィットさせる
            scaled_pixmap = pixmap.scaled(self.image_label.size(),
                                          Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation)
            self.image_label.setPixmap(scaled_pixmap)
        else:
            self.image_label.setText(f"Load Err:\n{os.path.basename(image_path)}")
            logger.warning(f"Failed to load thumbnail for: {image_path}")

    def _update_navigation_buttons(self) -> None:
        """ナビゲーションボタンの有効/無効状態を更新します。"""
        is_first = self.current_index <= 0
        is_last = self.current_index >= len(self.selected_images) - 1
        self.prev_button.setEnabled(not is_first and len(self.selected_images) > 0)
        self.next_button.setEnabled(not is_last and len(self.selected_images) > 0)

    def _update_comment_field(self) -> None:
        """コメント入力フィールドをキャッシュされた値で更新します。"""
        cached_comment = self.comment_cache.get(self.current_index, "") # なければ空文字
        self.comment_edit.setText(cached_comment)
        # logger.debug(f"Loaded comment for index {self.current_index}: '{cached_comment}'")

    def _get_positive_prompt(self, image_path: str) -> str:
        """画像からPositive Promptを抽出します。"""
        try:
            metadata_json = extract_metadata(image_path)
            metadata = json.loads(metadata_json)
            return metadata.get(MetadataKeys.POSITIVE, '')
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse metadata JSON for {image_path}: {e}")
            return f"[Error parsing metadata: {e}]"
        except Exception as e:
             logger.error(f"Failed to extract metadata for {image_path}: {e}", exc_info=True)
             return f"[Error extracting metadata: {e}]"


    def _display_prompt_lines(self, positive_prompt: str) -> None:
        """与えられたPositive Promptを行ごとに解析し、UIに表示します。"""
        self._clear_prompt_layout() # 既存の行をクリア
        self.prompt_checkboxes = []
        self.prompt_textboxes = []

        # プロンプトを改行で分割（空行は保持される可能性あり）
        lines = positive_prompt.splitlines() # split('\n') より splitlines() が良い場合も

        for i, line in enumerate(lines):
            line = line.strip() # 各行の前後の空白を除去
            if not line: # 空行はスキップ (オプション)
                 # logger.debug(f"Skipping empty line at index {i}")
                 continue

            line_layout = QHBoxLayout()

            # チェックボックス (行番号付き)
            checkbox = QCheckBox(f"{i+1}:")
            checkbox.stateChanged.connect(self._cache_current_state) # チェック変更時もキャッシュ更新
            self.prompt_checkboxes.append(checkbox)
            line_layout.addWidget(checkbox)

            # テキストボックス (読み取り専用)
            textbox = QLineEdit(line)
            textbox.setReadOnly(True)
            textbox.setFrame(False) # フレームを消してすっきり見せる
            # テキストボックスが長すぎる場合に省略表示する設定 (オプション)
            # textbox.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction) # 選択不可に
            # textbox.setToolTip(line) # 全文をツールチップで表示
            self.prompt_textboxes.append(textbox)
            line_layout.addWidget(textbox)

            self.prompt_layout.addLayout(line_layout)

        logger.debug(f"Displayed {len(self.prompt_checkboxes)} prompt lines.")

    def _apply_checkbox_state(self) -> None:
        """キャッシュされた、または前の画像のチェック状態を現在のチェックボックスに適用します。"""
        if self.current_index in self.checkbox_state_cache:
            # キャッシュされた状態があればそれを適用
            cached_states = self.checkbox_state_cache[self.current_index]
            if len(cached_states) == len(self.prompt_checkboxes):
                for cb, state in zip(self.prompt_checkboxes, cached_states):
                    cb.setChecked(state)
                logger.debug(f"Applied cached checkbox states for index {self.current_index}.")
            else:
                 logger.warning(f"Checkbox state cache mismatch for index {self.current_index}. Expected {len(self.prompt_checkboxes)}, got {len(cached_states)}. Resetting.")
                 # 状態が不一致ならデフォルト（すべてオフ）にする
                 for cb in self.prompt_checkboxes:
                     cb.setChecked(False)

        elif self.current_index > 0 and (self.current_index - 1) in self.checkbox_state_cache:
            # 前の画像のキャッシュがあればそれを引き継ぐ
            prev_states = self.checkbox_state_cache[self.current_index - 1]
            logger.debug(f"Applying previous checkbox states (from index {self.current_index - 1}) to index {self.current_index}.")
            for i, cb in enumerate(self.prompt_checkboxes):
                if i < len(prev_states):
                    cb.setChecked(prev_states[i])
                else:
                    cb.setChecked(False) # 行数が足りない場合はオフ
        else:
            # キャッシュも前の状態もない場合（最初の画像など）はすべてオフ
            logger.debug(f"Applying default checkbox states (all off) for index {self.current_index}.")
            for cb in self.prompt_checkboxes:
                cb.setChecked(False)
        # 適用後、念のため現在の状態をキャッシュ
        self._cache_current_state()


    def _clear_prompt_layout(self) -> None:
        """右パネルのプロンプト表示レイアウトの内容をクリアします。"""
        while self.prompt_layout.count():
            item = self.prompt_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            else:
                layout = item.layout()
                if layout:
                    # 再帰呼び出しではなく、内部のウィジェット/レイアウトを削除
                    self._clear_inner_layout(layout)
                    layout.deleteLater() # レイアウト自体も削除？ PyQtの挙動に依存

    def _clear_inner_layout(self, layout: QHBoxLayout) -> None:
         """QHBoxLayout内のウィジェットをクリアします。"""
         while layout.count():
              inner_item = layout.takeAt(0)
              inner_widget = inner_item.widget()
              if inner_widget:
                   inner_widget.deleteLater()
              else:
                   inner_layout = inner_item.layout()
                   if inner_layout:
                        self._clear_inner_layout(inner_layout) # 再帰が必要な場合
                        inner_layout.deleteLater()


    def show_previous_image(self) -> None:
        """前の画像を表示します。"""
        if self.current_index > 0:
            self._load_image_data(self.current_index - 1)

    def show_next_image(self) -> None:
        """次の画像を表示します。"""
        if self.current_index < len(self.selected_images) - 1:
            self._load_image_data(self.current_index + 1)

    def toggle_all_checkboxes(self) -> None:
        """表示されている全てのプロンプト行のチェックボックス状態を反転させます。"""
        if not hasattr(self, 'prompt_checkboxes') or not self.prompt_checkboxes:
            logger.warning("toggle_all_checkboxes: No checkboxes found.")
            return

        # 現在のチェック状態を確認（一つでもチェックが外れていれば、全てチェックする）
        all_checked = all(cb.isChecked() for cb in self.prompt_checkboxes)
        new_state = not all_checked # 新しい状態（全てチェック or 全て解除）

        # 全てのチェックボックスの状態を更新
        for checkbox in self.prompt_checkboxes:
            checkbox.setChecked(new_state)

        logger.info(f"Toggled all checkboxes to: {new_state}")
        # 状態変更後、キャッシュを更新
        self._cache_current_state()

    def _get_current_formatted_output(self, checked_only: bool = True) -> str:
        """現在の画像のプロンプト（チェックされたもののみ、または全て）とコメントを整形して返します。"""
        if not hasattr(self, 'prompt_textboxes') or not self.prompt_checkboxes:
            return ""

        # コメントを取得
        comment = self.comment_edit.text()

        # プロンプト行を取得
        selected_lines = []
        for checkbox, textbox in zip(self.prompt_checkboxes, self.prompt_textboxes):
            if not checked_only or checkbox.isChecked():
                line_text = textbox.text().strip() # textboxはLineEditに変更した
                if line_text:
                    selected_lines.append(line_text)

        # 共通フォーマット関数を使用
        return _format_output_string(comment, selected_lines, self.output_format)

    def copy_to_clipboard(self) -> None:
        """現在表示されている画像の、チェックされたプロンプトとコメントをクリップボードにコピーします。"""
        # 現在の状態をキャッシュしてから出力取得（重要）
        self._cache_current_state()
        output_text = self._get_current_formatted_output(checked_only=True)

        if output_text:
             QApplication.clipboard().setText(output_text)
             logger.info(f"Checked prompts copied to clipboard for index {self.current_index}.")
             # 成功メッセージを出すならここで (QStatusBar はないので print や logger)
             # print("Copied to clipboard!")
        else:
             logger.warning(f"No checked prompts to copy for index {self.current_index}.")
             # print("Nothing to copy.")


    def show_output_dialog(self, checked_only: bool = True) -> None:
        """
        Output Dialogを表示します。表示前に現在の状態をキャッシュします。
        """
        # 最新の状態をキャッシュ
        self._cache_current_state()
        logger.info(f"Showing Output Dialog (Checked only: {checked_only})")

        if not self.selected_images:
            QMessageBox.warning(self, "No Images", "There are no images to output.")
            return

        # OutputDialog を作成して表示
        dialog = OutputDialog(
            selected_images=self.selected_images,
            thumbnail_cache=self.thumbnail_cache,
            comment_cache=self.comment_cache,
            checkbox_cache=self.checkbox_state_cache, # キャッシュを渡す
            checked_only=checked_only,
            output_format=self.output_format,
            parent=self # 親ウィンドウとして WCCreatorDialog を設定
        )
        dialog.exec() # モーダルダイアログとして表示

# --- OutputDialog ---

class OutputDialog(QDialog):
    """
    WCCreatorDialogで編集された全ての画像のプロンプトとコメントを
    プレビュー・編集し、ファイルに出力するためのダイアログ。
    """
    def __init__(self,
                 selected_images: List[str],
                 thumbnail_cache: ThumbnailCache,
                 comment_cache: Dict[int, str],
                 checkbox_cache: Dict[int, List[bool]],
                 checked_only: bool,
                 output_format: str = OUTPUT_FORMAT_SEPARATE,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Output Preview & Editor")
        self.setGeometry(200, 200, OUTPUT_DIALOG_WIDTH, OUTPUT_DIALOG_HEIGHT) # 位置調整

        self.selected_images: List[str] = selected_images
        self.thumbnail_cache: ThumbnailCache = thumbnail_cache
        self.comment_cache: Dict[int, str] = comment_cache
        self.checkbox_cache: Dict[int, List[bool]] = checkbox_cache
        self.checked_only: bool = checked_only
        self.output_format: str = output_format

        # 各画像のUIウィジェットへの参照を保持するリスト
        # [{'comment': QLineEdit, 'prompt': QTextEdit}, ...]
        self.output_widgets: List[Dict[str, QWidget]] = []

        # UI要素のプレースホルダー
        self.scroll_area: QScrollArea = None
        self.scroll_content: QWidget = None
        self.scroll_layout: QVBoxLayout = None
        self.search_line_edit: QLineEdit = None
        self.replace_line_edit: QLineEdit = None
        self.replace_button: QPushButton = None
        self.output_button: QPushButton = None

        self.initUI()
        self._load_all_data()

    def initUI(self) -> None:
        """ダイアログのUIを初期化します。"""
        main_layout = QVBoxLayout(self)

        # 上部に検索・置換UIを追加
        main_layout.addLayout(self._create_replacement_ui())

        # スクロールエリア
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop) # 上詰め
        self.scroll_content.setLayout(self.scroll_layout)
        self.scroll_area.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll_area)

        # 下部に出力ボタン
        self.output_button = QPushButton("Save Output to File")
        self.output_button.clicked.connect(self.save_to_file)
        main_layout.addWidget(self.output_button)

    def _create_replacement_ui(self) -> QHBoxLayout:
        """検索・置換用のUIレイアウトを作成します。"""
        replacement_layout = QHBoxLayout()
        # 左側に検索・置換テキストボックス
        search_replace_vbox = QVBoxLayout()
        self.search_line_edit = QLineEdit()
        self.search_line_edit.setPlaceholderText("Find String")
        self.replace_line_edit = QLineEdit()
        self.replace_line_edit.setPlaceholderText("Replace With")
        search_replace_vbox.addWidget(QLabel("Find & Replace in Comments and Prompts:"))
        hbox = QHBoxLayout()
        hbox.addWidget(self.search_line_edit)
        hbox.addWidget(self.replace_line_edit)
        search_replace_vbox.addLayout(hbox)

        replacement_layout.addLayout(search_replace_vbox, 1) # Stretch factor 1

        # 右側にReplaceボタン
        self.replace_button = QPushButton("Replace All")
        self.replace_button.clicked.connect(self.replace_text)
        replacement_layout.addWidget(self.replace_button)

        return replacement_layout

    def _load_all_data(self) -> None:
        """全ての選択された画像のデータを読み込み、UIに表示します。"""
        # 既存のウィジェットをクリア (再ロード時に備える)
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.output_widgets = [] # ウィジェット参照リストもクリア
        logger.info(f"Loading data for {len(self.selected_images)} images into OutputDialog.")

        for i, image_path in enumerate(self.selected_images):
            # 各画像行のコンテナウィジェット
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 5, 0, 5) # 上下のマージン

            # --- 左側: サムネイル ---
            thumbnail_label = QLabel()
            pixmap = self.thumbnail_cache.get_thumbnail(image_path, OUTPUT_PREVIEW_THUMBNAIL_SIZE)
            if pixmap:
                # アスペクト比を保って表示
                scaled_pixmap = pixmap.scaled(OUTPUT_PREVIEW_THUMBNAIL_SIZE, OUTPUT_PREVIEW_THUMBNAIL_SIZE,
                                              Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation)
                thumbnail_label.setPixmap(scaled_pixmap)
            else:
                thumbnail_label.setText("Load Err")
            thumbnail_label.setFixedSize(OUTPUT_PREVIEW_THUMBNAIL_SIZE + 10, OUTPUT_PREVIEW_THUMBNAIL_SIZE + 10) # 少し余裕を持たせる
            thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumbnail_label.setStyleSheet("border: 1px solid lightgray;")
            row_layout.addWidget(thumbnail_label)

            # --- 右側: テキスト編集エリア ---
            text_widget = QWidget()
            text_layout = QVBoxLayout(text_widget)
            text_layout.setContentsMargins(0, 0, 0, 0)

            # コメント編集フィールド
            comment_edit = QLineEdit()
            comment = self.comment_cache.get(i, "") # キャッシュから取得
            comment_edit.setText(comment)
            comment_edit.setPlaceholderText("Comment")
            text_layout.addWidget(QLabel(f"{i+1}: Comment:"))
            text_layout.addWidget(comment_edit)

            # プロンプト編集フィールド
            prompt_edit = QTextEdit()
            prompt_edit.setAcceptRichText(False) # プレーンテキストのみ
            prompt_edit.setPlaceholderText("Positive Prompt")
            # プロンプト内容を取得・設定
            prompt_lines = self._get_prompt_lines_for_image(i, image_path)
            combined_prompt = " ".join(prompt_lines) # スペース区切りで結合
            prompt_edit.setPlainText(combined_prompt)
            prompt_edit.setMinimumHeight(80) # 最低限の高さを確保
            text_layout.addWidget(QLabel("Positive Prompt:"))
            text_layout.addWidget(prompt_edit)

            row_layout.addWidget(text_widget, 1) # Stretch factor 1
            self.scroll_layout.addWidget(row_widget)

            # 後でアクセスするためにウィジェットを保存
            self.output_widgets.append({
                'comment': comment_edit,
                'prompt': prompt_edit
            })

    def _get_prompt_lines_for_image(self, index: int, image_path: str) -> List[str]:
        """指定されたインデックスの画像のプロンプト行リストを取得します。"""
        selected_lines = []
        try:
            metadata_json = extract_metadata(image_path)
            metadata = json.loads(metadata_json)
            positive_prompt = metadata.get(MetadataKeys.POSITIVE, '')
            prompt_lines_all = [line.strip() for line in positive_prompt.splitlines() if line.strip()]

            if self.checked_only:
                # checked_only の場合、キャッシュされたチェック状態に基づいてフィルタリング
                if index in self.checkbox_cache:
                    checkbox_states = self.checkbox_cache[index]
                    for j, line in enumerate(prompt_lines_all):
                        if j < len(checkbox_states) and checkbox_states[j]:
                            selected_lines.append(line)
                else:
                    # チェック状態のキャッシュがない場合は空リスト
                    logger.warning(f"Checked only mode, but no checkbox cache found for index {index}.")
                    selected_lines = []
            else:
                # checked_only でない場合は全ての行を使用
                selected_lines = prompt_lines_all

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse metadata JSON for {image_path} in OutputDialog: {e}")
            return [f"[Error parsing metadata: {e}]"]
        except Exception as e:
             logger.error(f"Failed to extract metadata for {image_path} in OutputDialog: {e}", exc_info=True)
             return [f"[Error extracting metadata: {e}]"]

        return selected_lines


    def replace_text(self) -> None:
        """表示されている全てのコメントとプロンプトで文字列置換を実行します。"""
        search_str = self.search_line_edit.text()
        replace_str = self.replace_line_edit.text()

        if not search_str:
            QMessageBox.warning(self, "Empty Search String", "Please enter the string to find.")
            return

        replaced_count_total = 0
        logger.info(f"Replacing '{search_str}' with '{replace_str}' in all fields.")

        for i, widgets in enumerate(self.output_widgets):
            comment_widget = widgets['comment']
            prompt_widget = widgets['prompt']
            replaced_count_item = 0

            # コメント欄の置換
            original_comment = comment_widget.text()
            new_comment = original_comment.replace(search_str, replace_str)
            if original_comment != new_comment:
                 comment_widget.setText(new_comment)
                 replaced_count_item += original_comment.count(search_str)

            # プロンプト欄の置換
            original_prompt = prompt_widget.toPlainText()
            new_prompt = original_prompt.replace(search_str, replace_str)
            if original_prompt != new_prompt:
                 prompt_widget.setPlainText(new_prompt)
                 replaced_count_item += original_prompt.count(search_str)

            if replaced_count_item > 0:
                 logger.debug(f"Replaced {replaced_count_item} occurrences in item {i+1}.")
                 replaced_count_total += replaced_count_item

        logger.info(f"Total replacements made: {replaced_count_total}")
        if replaced_count_total > 0:
             QMessageBox.information(self, "Replacement Complete",
                                     f"Replaced {replaced_count_total} occurrences.")
        else:
             QMessageBox.information(self, "Replacement Complete",
                                     f"The string '{search_str}' was not found.")

    def get_output_text(self) -> str:
        """
        現在のUIの状態から最終的な出力テキストを生成します。
        """
        output_lines = []
        for widgets in self.output_widgets:
            comment = widgets['comment'].text() # strip は format 関数内で
            # prompt は QTextEdit なので toPlainText() で取得
            prompt_text = widgets['prompt'].toPlainText()
            # QTextEdit は改行を含む可能性があるので、スペース区切りにするために行リストに変換
            prompt_lines = [line.strip() for line in prompt_text.splitlines() if line.strip()]

            # 共通フォーマット関数を使用
            formatted_line = _format_output_string(comment, prompt_lines, self.output_format)
            if formatted_line: # 空でなければ追加
                 output_lines.append(formatted_line)

        # 各画像の出力を改行で結合
        return "\n".join(output_lines)

    def save_to_file(self) -> None:
        """現在の内容をテキストファイルに保存します。"""
        output_text = self.get_output_text()
        if not output_text:
            QMessageBox.warning(self, "Empty Output", "There is no content to save.")
            return

        # ファイル保存ダイアログを表示
        suggested_filename = "wc_creator_output.txt" # デフォルトファイル名
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Output File", suggested_filename, "Text Files (*.txt);;All Files (*)"
        )

        if file_path:
            logger.info(f"Saving output to file: {file_path}")
            try:
                # newline='\r\n' はWindows標準の改行コード (CRLF)
                # newline='\n'   はUnix/Linux標準 (LF)
                # encoding='utf-8' は必須
                with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(output_text)
                logger.info("File saved successfully.")
                QMessageBox.information(self, "Save Successful", f"Output saved to:\n{file_path}")
                # 保存後にダイアログを閉じる場合
                # self.accept()
            except IOError as e:
                error_msg = f"Failed to save file due to IO error: {e}"
                logger.error(error_msg, exc_info=True)
                QMessageBox.critical(self, "Save Error", f"{error_msg}\nPlease check file permissions or path.")
            except Exception as e:
                error_msg = f"An unexpected error occurred during file saving: {e}"
                logger.error(error_msg, exc_info=True)
                QMessageBox.critical(self, "Save Error", error_msg)