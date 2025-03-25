# modules/image_dialog.py
import json
import os
import re
from PyQt6.QtWidgets import (QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QTextBrowser, 
                            QApplication, QScrollArea, QTabWidget, QTextEdit, QWidget)
from PyQt6.QtGui import QPixmap, QTextCursor, QTextCharFormat, QColor
from PyQt6.QtCore import Qt, QPoint, pyqtSignal, QEvent

class TagTextBrowser(QTextBrowser):
    tagClicked = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setOpenExternalLinks(False)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.selected_tags = set()
        self.tag_positions = []
        self.drag_start_pos = None
        self.viewport().installEventFilter(self)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            scroll_pos = self.verticalScrollBar().value()
            cursor = self.cursorForPosition(event.pos())
            position = cursor.position()
            
            self.drag_start_pos = position
            
            for start, end, tag_text in self.tag_positions:
                if start <= position <= end:
                    if tag_text in self.selected_tags:
                        self.selected_tags.remove(tag_text)
                    else:
                        self.selected_tags.add(tag_text)
                    self.update_highlight()
                    event.accept()
                    self.verticalScrollBar().setValue(scroll_pos)
                    return
            
            super().mousePressEvent(event)
            self.verticalScrollBar().setValue(scroll_pos)
    
    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self.drag_start_pos is not None:
            scroll_pos = self.verticalScrollBar().value()
            cursor = self.cursorForPosition(event.pos())
            current_pos = cursor.position()
            
            start_pos = min(self.drag_start_pos, current_pos)
            end_pos = max(self.drag_start_pos, current_pos)
            
            self.selected_tags.clear()
            for start, end, tag_text in self.tag_positions:
                if start <= end_pos and end >= start_pos:
                    self.selected_tags.add(tag_text)
            
            self.update_highlight()
            event.accept()
            self.verticalScrollBar().setValue(scroll_pos)
        else:
            super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = None
            super().mouseReleaseEvent(event)
    
    def eventFilter(self, obj, event):
        if obj == self.viewport() and event.type() == QEvent.Type.MouseButtonPress:
            return False
        return super().eventFilter(obj, event)
    
    def clear_selection(self):
        self.selected_tags.clear()
        self.update_highlight()
    
    def update_highlight(self):
        current_cursor = self.textCursor()
        saved_position = current_cursor.position()
        
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        format = QTextCharFormat()
        cursor.setCharFormat(format)
        cursor.clearSelection()
        
        for start, end, tag_text in self.tag_positions:
            if tag_text in self.selected_tags:
                cursor.setPosition(start)
                cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
                format = QTextCharFormat()
                format.setBackground(QColor(255, 165, 0))
                cursor.setCharFormat(format)
                cursor.clearSelection()
        
        cursor.setPosition(saved_position)
        self.setTextCursor(cursor)
    
    def parse_and_set_text(self, text):
        self.clear()
        self.selected_tags = set()
        self.tag_positions = []
        
        if not text:
            self.setPlainText("")
            return
        
        self.setPlainText(text)
        
        # タグを検出するための状態変数
        i = 0
        text_length = len(text)
        
        while i < text_length:
            # 空白をスキップ
            while i < text_length and text[i].isspace():
                i += 1
            
            if i >= text_length:
                break
            
            start = i
            
            # カッコ内のタグ処理
            if text[i] == '(':
                bracket_count = 1
                i += 1
                while i < text_length and bracket_count > 0:
                    if text[i] == '(':
                        bracket_count += 1
                    elif text[i] == ')':
                        bracket_count -= 1
                    i += 1
                tag_text = text[start:i].strip()
                self.tag_positions.append((start, i, tag_text))
            
            # 角括弧内のタグ処理 
            elif text[i] == '<':
                i += 1
                while i < text_length and text[i] != '>':
                    i += 1
                if i < text_length:  # '>'が見つかった場合
                    i += 1  # '>'も含める
                tag_text = text[start:i].strip()
                self.tag_positions.append((start, i, tag_text))
            
            # エスケープされた括弧のタグ処理 \(...\)
            elif i < text_length - 1 and text[i] == '\\' and text[i+1] == '(':
                # エスケープされた開き括弧を検出
                i += 2  # \( をスキップ
                while i < text_length:
                    # エスケープされた閉じ括弧を検索
                    if i < text_length - 1 and text[i] == '\\' and text[i+1] == ')':
                        i += 2  # \) も含める
                        break
                    i += 1
                tag_text = text[start:i].strip()
                self.tag_positions.append((start, i, tag_text))
            
            # 通常のタグ処理（カンマまで）
            else:
                escape_sequence = False
                while i < text_length:
                    # エスケープシーケンスの処理
                    if text[i] == '\\' and i + 1 < text_length:
                        escape_sequence = True
                        i += 2  # バックスラッシュと次の文字をスキップ
                        continue
                    
                    # カンマか特殊文字（エスケープされていない）が見つかったらタグ終了
                    if text[i] == ',' or (not escape_sequence and (text[i] == '<' or text[i] == '(')):
                        break
                    
                    escape_sequence = False
                    i += 1
                
                # カンマが見つかった場合、そこまでをタグとする
                if i < text_length and text[i] == ',':
                    tag_text = text[start:i].strip()
                    if tag_text:  # 空でなければタグとして追加
                        self.tag_positions.append((start, i, tag_text))
                    i += 1  # カンマをスキップ
                # 特殊文字が見つかった場合、そこまでをタグとする
                elif i < text_length and (text[i] == '<' or text[i] == '('):
                    tag_text = text[start:i].strip()
                    if tag_text:  # 空でなければタグとして追加
                        self.tag_positions.append((start, i, tag_text))
                    # 位置は進めない（次のループで特殊タグとして処理）
                # 文字列の終わりまで達した場合
                else:
                    tag_text = text[start:i].strip()
                    if tag_text:  # 空でなければタグとして追加
                        self.tag_positions.append((start, i, tag_text))
        
        # デバッグ用
        print("Detected tags:")
        for start, end, tag in self.tag_positions:
            print(f"  '{tag}' at {start}-{end}")
    
    def get_selected_tags(self):
        # 単にセットを返すのではなく、元の順序を維持した選択タグのリストを返す
        ordered_selected_tags = []
        for start, end, tag_text in self.tag_positions:
            if tag_text in self.selected_tags:
                ordered_selected_tags.append(tag_text)
        return ordered_selected_tags

class MetadataDialog(QDialog):
    def __init__(self, metadata, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Metadata")
        self.metadata_dict = json.loads(metadata) if isinstance(metadata, str) else metadata
        
        # タブウィジェットの設定
        self.tab_widget = QTabWidget(self)
        
        # "Metadata" タブ
        self.metadata_tab = QWidget()
        self.setup_metadata_tab()
        self.tab_widget.addTab(self.metadata_tab, "Metadata")
        
        # "Select" タブ
        self.select_tab = QWidget()
        self.setup_select_tab()
        self.tab_widget.addTab(self.select_tab, "Select")
        
        # 初期タブを "Metadata" に設定
        self.tab_widget.setCurrentIndex(0)
        
        # レイアウトの設定
        layout = QVBoxLayout()
        layout.addWidget(self.tab_widget)
        
        # Clipboard と Clear Selection ボタン
        button_layout = QHBoxLayout()
        self.clipboard_button = QPushButton("Clipboard")
        self.clipboard_button.clicked.connect(self.copy_to_clipboard)
        button_layout.addStretch()
        button_layout.addWidget(self.clipboard_button)
        
        self.clear_button = QPushButton("Clear Selection")
        self.clear_button.clicked.connect(self.clear_all_selections)
        button_layout.addWidget(self.clear_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        self.setMinimumSize(400, 600)
    
    def setup_metadata_tab(self):
        """Metadataタブの設定（通常のテキスト表示）"""
        layout = QVBoxLayout()
        
        # テキストエリアの設定
        self.metadata_positive_edit = QTextEdit(self)
        self.metadata_negative_edit = QTextEdit(self)
        self.metadata_others_edit = QTextEdit(self)
        
        self.metadata_positive_edit.setPlainText(self.metadata_dict.get("positive_prompt", "No positive metadata"))
        self.metadata_negative_edit.setPlainText(self.metadata_dict.get("negative_prompt", "No negative metadata"))
        self.metadata_others_edit.setPlainText(self.metadata_dict.get("generation_info", "No generation info"))
        
        self.metadata_positive_edit.setReadOnly(True)
        self.metadata_negative_edit.setReadOnly(True)
        self.metadata_others_edit.setReadOnly(True)
        
        # 選択変更時のシグナルを接続
        self.metadata_positive_edit.selectionChanged.connect(lambda: self.clear_other_selections(self.metadata_positive_edit, "metadata"))
        self.metadata_negative_edit.selectionChanged.connect(lambda: self.clear_other_selections(self.metadata_negative_edit, "metadata"))
        self.metadata_others_edit.selectionChanged.connect(lambda: self.clear_other_selections(self.metadata_others_edit, "metadata"))
        
        # フォーカス時の選択解除
        self.metadata_positive_edit.focusInEvent = lambda event: self.clear_other_selections(self.metadata_positive_edit, "metadata")
        self.metadata_negative_edit.focusInEvent = lambda event: self.clear_other_selections(self.metadata_negative_edit, "metadata")
        self.metadata_others_edit.focusInEvent = lambda event: self.clear_other_selections(self.metadata_others_edit, "metadata")
        
        # レイアウトに追加
        layout.addWidget(QLabel("Positive"))
        layout.addWidget(self.metadata_positive_edit)
        layout.addWidget(QLabel("Negative"))
        layout.addWidget(self.metadata_negative_edit)
        layout.addWidget(QLabel("Other"))
        layout.addWidget(self.metadata_others_edit)
        
        self.metadata_tab.setLayout(layout)
    
    def setup_select_tab(self):
        """Selectタブの設定（タグ選択機能）"""
        layout = QVBoxLayout()
        
        # カスタムQTextBrowserの設定
        self.select_positive_browser = TagTextBrowser(self)
        self.select_negative_browser = TagTextBrowser(self)
        self.select_others_browser = TagTextBrowser(self)
        
        self.select_positive_browser.parse_and_set_text(self.metadata_dict.get("positive_prompt", "No positive metadata"))
        self.select_negative_browser.parse_and_set_text(self.metadata_dict.get("negative_prompt", "No negative metadata"))
        self.select_others_browser.parse_and_set_text(self.metadata_dict.get("generation_info", "No generation info"))
        
        # ブラウザ間の相互作用
        self.select_positive_browser.mousePressEvent = lambda event: self.handle_mouse_press(event, self.select_positive_browser)
        self.select_negative_browser.mousePressEvent = lambda event: self.handle_mouse_press(event, self.select_negative_browser)
        self.select_others_browser.mousePressEvent = lambda event: self.handle_mouse_press(event, self.select_others_browser)
        
        # レイアウトに追加
        layout.addWidget(QLabel("Positive"))
        layout.addWidget(self.select_positive_browser)
        layout.addWidget(QLabel("Negative"))
        layout.addWidget(self.select_negative_browser)
        layout.addWidget(QLabel("Other"))
        layout.addWidget(self.select_others_browser)
        
        self.select_tab.setLayout(layout)
    
    def handle_mouse_press(self, event, current_browser):
        browsers = [self.select_positive_browser, self.select_negative_browser, self.select_others_browser]
        for browser in browsers:
            if browser != current_browser:
                browser.clear_selection()
        TagTextBrowser.mousePressEvent(current_browser, event)
    
    def clear_other_selections(self, current_edit, tab_type):
        """指定されたタブ内で他のテキストエリアの選択を解除"""
        if tab_type == "metadata":
            edits = [self.metadata_positive_edit, self.metadata_negative_edit, self.metadata_others_edit]
        else:  # "select" タブは使用しないが、将来のために残す
            return
        
        for text_edit in edits:
            if text_edit != current_edit and text_edit.textCursor().hasSelection():
                cursor = text_edit.textCursor()
                cursor.clearSelection()
                text_edit.setTextCursor(cursor)
    
    def copy_to_clipboard(self):
        """選択されたテキストまたはタグをクリップボードにコピー"""
        current_tab = self.tab_widget.currentWidget()
        
        if current_tab == self.metadata_tab:
            for text_edit in [self.metadata_positive_edit, self.metadata_negative_edit, self.metadata_others_edit]:
                selected_text = text_edit.textCursor().selectedText()
                if selected_text:
                    clipboard = QApplication.clipboard()
                    clipboard.setText(selected_text)
                    print(f"Copied: {selected_text}")
                    break
        elif current_tab == self.select_tab:
            for browser in [self.select_positive_browser, self.select_negative_browser, self.select_others_browser]:
                selected_tags = browser.get_selected_tags()
                if selected_tags:
                    # タグの順序を保持するために、元のメタデータ順に並べ替える
                    ordered_tags = []
                    for start, end, tag_text in browser.tag_positions:
                        if tag_text in selected_tags:
                            ordered_tags.append(tag_text)
                    
                    selected_text = ", ".join(ordered_tags)
                    clipboard = QApplication.clipboard()
                    clipboard.setText(selected_text)
                    print(f"Copied: {selected_text}")
                    break
    
    def clear_all_selections(self):
        """現在のタブに応じて選択を解除"""
        current_tab = self.tab_widget.currentWidget()
        
        if current_tab == self.metadata_tab:
            for text_edit in [self.metadata_positive_edit, self.metadata_negative_edit, self.metadata_others_edit]:
                cursor = text_edit.textCursor()
                cursor.clearSelection()
                text_edit.setTextCursor(cursor)
        elif current_tab == self.select_tab:
            for browser in [self.select_positive_browser, self.select_negative_browser, self.select_others_browser]:
                browser.clear_selection()
    
    def update_metadata(self, metadata):
        """メタデータを更新"""
        try:
            self.metadata_dict = json.loads(metadata) if isinstance(metadata, str) else metadata
            # Metadataタブ
            self.metadata_positive_edit.setPlainText(self.metadata_dict.get("positive_prompt", "No positive metadata"))
            self.metadata_negative_edit.setPlainText(self.metadata_dict.get("negative_prompt", "No negative metadata"))
            self.metadata_others_edit.setPlainText(self.metadata_dict.get("generation_info", "No generation info"))
            # Selectタブ
            self.select_positive_browser.parse_and_set_text(self.metadata_dict.get("positive_prompt", "No positive metadata"))
            self.select_negative_browser.parse_and_set_text(self.metadata_dict.get("negative_prompt", "No negative metadata"))
            self.select_others_browser.parse_and_set_text(self.metadata_dict.get("generation_info", "No generation info"))
            self.clear_all_selections()
        except Exception as e:
            print(f"Error updating metadata: {e}")

class ImageDialog(QDialog):
    def __init__(self, image_path, preview_mode='seamless', parent=None):
        super().__init__(parent)
        self.setWindowTitle("Full Image")
        self.preview_mode = preview_mode
        self.scale_factor = 1.0
        self.saved_geometry = None
        self.image_path = image_path
        self.parent_window = parent
        
        self.all_images = self.get_all_images()
        self.current_index = self.all_images.index(image_path) if image_path in self.all_images else 0
        
        self.layout = QVBoxLayout()
        
        self.tool_layout = QHBoxLayout()
        
        self.prev_button = QPushButton("← Previous")
        self.prev_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.prev_button.clicked.connect(self.show_previous_image)
        self.prev_button.setEnabled(self.current_index > 0)
        
        self.next_button = QPushButton("Next →")
        self.next_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.next_button.clicked.connect(self.show_next_image)
        self.next_button.setEnabled(self.current_index < len(self.all_images) - 1)
        
        self.counter_label = QLabel(f"{self.current_index + 1} / {len(self.all_images)}")
        self.counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.tool_layout.addWidget(self.prev_button)
        self.tool_layout.addWidget(self.counter_label)
        self.tool_layout.addWidget(self.next_button)
        self.tool_layout.addStretch()
        
        self.maximize_button = QPushButton("□")
        self.maximize_button.setFixedSize(30, 30)
        self.maximize_button.clicked.connect(self.toggle_maximize)
        self.tool_layout.addWidget(self.maximize_button)
        
        self.layout.addLayout(self.tool_layout)
        
        if self.preview_mode == 'seamless':
            self.setup_seamless_mode(image_path)
        else:
            self.setup_wheel_mode(image_path)
            
        self.setLayout(self.layout)
        self.setMinimumSize(600, 500)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def get_all_images(self):
        if not self.parent_window:
            return [self.image_path]
        if hasattr(self.parent_window, 'filter_results') and self.parent_window.filter_results:
            return self.parent_window.filter_results
        elif hasattr(self.parent_window, 'images'):
            return self.parent_window.images
        else:
            return [self.image_path]

    def show_next_image(self):
        if self.current_index < len(self.all_images) - 1:
            self.current_index += 1
            self.load_image(self.all_images[self.current_index])
            self.update_navigation_buttons()

    def show_previous_image(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.load_image(self.all_images[self.current_index])
            self.update_navigation_buttons()

    def load_image(self, image_path):
        self.image_path = image_path
        self.pixmap = QPixmap(image_path)
        self.setWindowTitle(f"Full Image - {os.path.basename(image_path)}")
        
        if self.preview_mode == 'seamless':
            scaled_pixmap = self.pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.image_label.setPixmap(scaled_pixmap)
        else:
            self.scale_factor = 1.0
            self.image_label.setPixmap(self.pixmap)

    def update_navigation_buttons(self):
        self.prev_button.setEnabled(self.current_index > 0)
        self.next_button.setEnabled(self.current_index < len(self.all_images) - 1)
        self.counter_label.setText(f"{self.current_index + 1} / {len(self.all_images)}")

    def setup_seamless_mode(self, image_path):
        self.image_label = QLabel(self)
        self.pixmap = QPixmap(image_path)
        scaled_pixmap = self.pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.image_label.setPixmap(scaled_pixmap)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.image_label)

    def setup_wheel_mode(self, image_path):
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.image_label = QLabel()
        self.pixmap = QPixmap(image_path)
        self.image_label.setPixmap(self.pixmap)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidget(self.image_label)
        self.scroll_area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.layout.addWidget(self.scroll_area)
        self.setToolTip("Ctrl + Wheel to zoom, drag to scroll")
        self.resize(1000, 900)

    def wheelEvent(self, event):
        if self.preview_mode == 'wheel':
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                delta = event.angleDelta().y()
                if delta > 0:
                    self.scale_factor *= 1.1
                else:
                    self.scale_factor *= 0.9
                scaled_pixmap = self.pixmap.scaled(
                    self.pixmap.size() * self.scale_factor,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.image_label.setPixmap(scaled_pixmap)
            else:
                self.scroll_area.verticalScrollBar().setValue(
                    self.scroll_area.verticalScrollBar().value() - event.angleDelta().y()
                )

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Right or event.key() == Qt.Key.Key_Space:
            self.show_next_image()
        elif event.key() == Qt.Key.Key_Left or event.key() == Qt.Key.Key_Backspace:
            self.show_previous_image()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if self.preview_mode == 'wheel' and (self.image_label.size().width() > self.size().width() or self.image_label.size().height() > self.size().height()):
            self.drag_start = event.pos()
            self.scroll_start_v = self.scroll_area.verticalScrollBar().value()
            self.scroll_start_h = self.scroll_area.horizontalScrollBar().value()

    def mouseMoveEvent(self, event):
        if self.preview_mode == 'wheel' and (self.image_label.size().width() > self.size().width() or self.image_label.size().height() > self.size().height()):
            delta = event.pos() - self.drag_start
            self.scroll_area.verticalScrollBar().setValue(self.scroll_start_v - delta.y())
            self.scroll_area.horizontalScrollBar().setValue(self.scroll_start_h - delta.x())

    def resizeEvent(self, event):
        if self.preview_mode == 'seamless':
            new_pixmap = self.pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.image_label.setPixmap(new_pixmap)
        else:
            super().resizeEvent(event)

    def toggle_maximize(self):
        if self.windowState() != Qt.WindowState.WindowMaximized:
            if self.saved_geometry is None:
                self.saved_geometry = self.saveGeometry()
            self.setWindowState(Qt.WindowState.WindowMaximized)
            self.maximize_button.setText("❐")
        else:
            if self.saved_geometry:
                self.restoreGeometry(self.saved_geometry)
                self.setWindowState(Qt.WindowState.WindowNoState)
                self.maximize_button.setText("□")
                self.saved_geometry = None

if __name__ == "__main__":
    app = QApplication([])
    metadata = '''
    {
        "positive_prompt": "masterpiece, (worst quality, low quality:1.2), best quality",
        "negative_prompt": "(bad anatomy, blurry:0.8), lowres",
        "generation_info": "512x512, 50 steps"
    }
    '''
    dialog = MetadataDialog(metadata)
    dialog.exec()