# modules/wc_creator.py
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QSplitter, QLabel, 
    QTextEdit, QCheckBox, QScrollArea, QWidget, QLineEdit, 
    QFileDialog, QApplication, QGridLayout
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap

class WCCreatorDialog(QDialog):
    def __init__(self, selected_images, thumbnail_cache, parent=None):
        super().__init__(parent)
        self.setWindowTitle("WC Creator")
        self.setGeometry(100, 100, 900, 600)
        self.selected_images = selected_images
        self.thumbnail_cache = thumbnail_cache
        self.current_index = 0
        self.comment_cache = {}  # Cache for comment text
        self.checkbox_state_cache = {}  # Cache for checkbox states
        
        self.initUI()
        self.load_image_data(self.current_index)
    
    def initUI(self):
        main_layout = QHBoxLayout(self)
        
        # Create splitter for left (1/3) and right (2/3) sections
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left panel (image view)
        self.left_panel = QWidget()
        left_layout = QVBoxLayout(self.left_panel)
        
        # Thumbnail display
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(250, 250)
        left_layout.addWidget(self.image_label)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        self.prev_button = QPushButton("←")
        self.prev_button.clicked.connect(self.show_previous_image)
        self.next_button = QPushButton("→")
        self.next_button.clicked.connect(self.show_next_image)
        nav_layout.addWidget(self.prev_button)
        nav_layout.addWidget(self.next_button)
        left_layout.addLayout(nav_layout)
        
        # Right panel
        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)
        
        # Top controls
        top_layout = QHBoxLayout()
        self.all_button = QPushButton("ALL")
        self.all_button.clicked.connect(self.toggle_all_checkboxes)
        self.comment_edit = QLineEdit()
        self.comment_edit.setPlaceholderText("Enter comment")
        top_layout.addWidget(self.all_button)
        top_layout.addWidget(QLabel("Comment:"))
        top_layout.addWidget(self.comment_edit)
        right_layout.addLayout(top_layout)
        
        # Scroll area for prompt lines
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.prompt_layout = QVBoxLayout(self.scroll_content)
        self.scroll_area.setWidget(self.scroll_content)
        right_layout.addWidget(self.scroll_area)
        
        # Bottom buttons
        bottom_layout = QHBoxLayout()
        self.output_checked_button = QPushButton("Output Checked")
        self.output_checked_button.clicked.connect(lambda: self.show_output_dialog(checked_only=True))
        self.output_all_button = QPushButton("Output All")
        self.output_all_button.clicked.connect(lambda: self.show_output_dialog(checked_only=False))
        self.clipboard_button = QPushButton("Clipboard")
        self.clipboard_button.clicked.connect(self.copy_to_clipboard)
        
        bottom_layout.addWidget(self.output_checked_button)
        bottom_layout.addWidget(self.output_all_button)
        bottom_layout.addWidget(self.clipboard_button)
        right_layout.addLayout(bottom_layout)
        
        # Add panels to splitter with proper size ratio (1:2)
        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.right_panel)
        self.splitter.setSizes([300, 600])
        
        main_layout.addWidget(self.splitter)
    
    def load_image_data(self, index):
        if not self.selected_images or index < 0 or index >= len(self.selected_images):
            return
        
        # Cache current comment and checkbox states if needed
        if hasattr(self, 'prompt_checkboxes') and self.current_index < len(self.selected_images):
            self.comment_cache[self.current_index] = self.comment_edit.text()
            self.checkbox_state_cache[self.current_index] = [cb.isChecked() for cb in self.prompt_checkboxes]
        
        # Update current index and image path
        self.current_index = index
        current_image = self.selected_images[index]
        
        # Update image display
        pixmap = self.thumbnail_cache.get_thumbnail(current_image, 250)
        if pixmap:
            self.image_label.setPixmap(pixmap)
        
        # Update navigation buttons
        self.prev_button.setEnabled(index > 0)
        self.next_button.setEnabled(index < len(self.selected_images) - 1)
        
        # Load comment from cache if available
        if index in self.comment_cache:
            self.comment_edit.setText(self.comment_cache[index])
        else:
            self.comment_edit.clear()
        
        # Extract and display prompt data
        from modules.metadata import extract_metadata
        metadata_json = extract_metadata(current_image)
        import json
        metadata = json.loads(metadata_json)
        
        positive_prompt = metadata.get('positive_prompt', '')
        
        # Clear previous content
        self.clear_prompt_layout()
        
        # Split prompt by newlines only (keep commas intact)
        lines = positive_prompt.split('\n')
        
        # Create checkbox and text for each line
        self.prompt_checkboxes = []
        self.prompt_textboxes = []
        
        for i, line in enumerate(lines):
            line_layout = QHBoxLayout()
            
            # Line number and checkbox
            checkbox = QCheckBox(f"{i+1}:")
            self.prompt_checkboxes.append(checkbox)
            line_layout.addWidget(checkbox)
            
            # Text box
            textbox = QLineEdit(line)
            textbox.setReadOnly(True)
            self.prompt_textboxes.append(textbox)
            line_layout.addWidget(textbox)
            
            self.prompt_layout.addLayout(line_layout)
        
        # Apply cached checkbox states if available
        if index in self.checkbox_state_cache and len(self.checkbox_state_cache[index]) == len(self.prompt_checkboxes):
            for cb, state in zip(self.prompt_checkboxes, self.checkbox_state_cache[index]):
                cb.setChecked(state)
        elif not self.checkbox_state_cache:
            # For the first image, initialize all checkboxes as unchecked
            for cb in self.prompt_checkboxes:
                cb.setChecked(False)
        else:
            # For subsequent images, carry over checked states from previous image
            prev_states = self.checkbox_state_cache.get(self.current_index - 1, [])
            for i, cb in enumerate(self.prompt_checkboxes):
                if i < len(prev_states):
                    cb.setChecked(prev_states[i])
                else:
                    cb.setChecked(False)
    
    def clear_prompt_layout(self):
        # Clear all widgets from prompt layout
        while self.prompt_layout.count():
            item = self.prompt_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self.clear_layout(item.layout())
    
    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self.clear_layout(item.layout())
    
    def show_previous_image(self):
        if self.current_index > 0:
            self.load_image_data(self.current_index - 1)
    
    def show_next_image(self):
        if self.current_index < len(self.selected_images) - 1:
            self.load_image_data(self.current_index + 1)
    
    def toggle_all_checkboxes(self):
        if not hasattr(self, 'prompt_checkboxes') or not self.prompt_checkboxes:
            return
        
        # Check if all are currently checked
        all_checked = all(cb.isChecked() for cb in self.prompt_checkboxes)
        
        # Toggle all checkboxes
        for checkbox in self.prompt_checkboxes:
            checkbox.setChecked(not all_checked)
        
        # Update cache
        self.checkbox_state_cache[self.current_index] = [cb.isChecked() for cb in self.prompt_checkboxes]
    
    def get_formatted_output(self, checked_only=True):
        if not hasattr(self, 'prompt_textboxes') or not self.prompt_checkboxes:
            return ""
        
        # Get comment
        comment = self.comment_edit.text().strip()
        
        # Get checked or all prompt lines
        selected_lines = []
        for checkbox, textbox in zip(self.prompt_checkboxes, self.prompt_textboxes):
            if not checked_only or checkbox.isChecked():
                line_text = textbox.text()
                if line_text:  # Skip empty lines
                    selected_lines.append(line_text)
        
        # Join lines without adding commas
        combined_prompt = " ".join(selected_lines)
        
        # Format output according to spec
        if comment:
            return f"# {comment}\n{combined_prompt}"
        else:
            return combined_prompt
    
    def copy_to_clipboard(self):
        output_text = self.get_formatted_output(checked_only=True)
        QApplication.clipboard().setText(output_text)
    
    def show_output_dialog(self, checked_only=True):
        # Cache current state
        self.comment_cache[self.current_index] = self.comment_edit.text()
        self.checkbox_state_cache[self.current_index] = [cb.isChecked() for cb in self.prompt_checkboxes]
        
        # Create and show output dialog
        dialog = OutputDialog(self.selected_images, self.thumbnail_cache, 
                              self.comment_cache, self.checkbox_state_cache,
                              checked_only, self)
        dialog.exec()


class OutputDialog(QDialog):
    def __init__(self, selected_images, thumbnail_cache, comment_cache, 
                 checkbox_cache, checked_only, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Output Preview")
        self.setGeometry(100, 100, 1000, 700)
        self.selected_images = selected_images
        self.thumbnail_cache = thumbnail_cache
        self.comment_cache = comment_cache
        self.checkbox_cache = checkbox_cache
        self.checked_only = checked_only
        
        self.text_data = []  # Store generated text for each image
        
        self.initUI()
        self.load_all_data()
    
    def initUI(self):
        main_layout = QVBoxLayout(self)
        
        # Scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_area.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll_area)
        
        # Output button
        self.output_button = QPushButton("Output")
        self.output_button.clicked.connect(self.save_to_file)
        main_layout.addWidget(self.output_button)
    
    def load_all_data(self):
        from modules.metadata import extract_metadata
        import json
        
        self.output_widgets = []
        
        for i, image_path in enumerate(self.selected_images):
            # Container for each image row
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            
            # Image thumbnail
            thumbnail_label = QLabel()
            pixmap = self.thumbnail_cache.get_thumbnail(image_path, 150)
            if pixmap:
                thumbnail_label.setPixmap(pixmap)
            thumbnail_label.setFixedSize(150, 150)
            thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row_layout.addWidget(thumbnail_label)
            
            # Text content area
            text_widget = QWidget()
            text_layout = QVBoxLayout(text_widget)
            
            # Comment field
            comment_label = QLabel("Comment:")
            comment_edit = QLineEdit()
            comment = self.comment_cache.get(i, "")
            comment_edit.setText(comment)
            text_layout.addWidget(comment_label)
            text_layout.addWidget(comment_edit)
            
            # Prompt content
            prompt_label = QLabel("Positive Prompt:")
            text_layout.addWidget(prompt_label)
            
            # Get prompt content
            metadata_json = extract_metadata(image_path)
            metadata = json.loads(metadata_json)
            positive_prompt = metadata.get('positive_prompt', '')
            prompt_lines = positive_prompt.split('\n')
            
            # Generate formatted text
            selected_lines = []
            if self.checked_only:
                # Output Checkedの場合は、チェック状態がキャッシュされている場合のみ行を出力
                if i in self.checkbox_cache:
                    checkboxes = self.checkbox_cache[i]
                    for j, line in enumerate(prompt_lines):
                        if j < len(checkboxes) and checkboxes[j]:
                            if line.strip():
                                selected_lines.append(line)
                # キャッシュがない場合は、何も追加しない（改行も無し）
            else:
                # Output ALLの場合は、必ず全行出力する
                for line in prompt_lines:
                    if line.strip():
                        selected_lines.append(line)
            
            # Combine without adding extra commas, joined by space
            combined_prompt = " ".join(selected_lines)
            
            # Prompt edit field
            prompt_edit = QTextEdit()
            prompt_edit.setPlainText(combined_prompt)
            prompt_edit.setMinimumHeight(80)
            text_layout.addWidget(prompt_edit)
            
            row_layout.addWidget(text_widget)
            self.scroll_layout.addWidget(row_widget)
            
            # Store widgets for later access
            self.output_widgets.append({
                'comment': comment_edit,
                'prompt': prompt_edit
            })

    def get_output_text(self):
        output_lines = []
        
        for widgets in self.output_widgets:
            comment = widgets['comment'].text().strip()
            prompt = widgets['prompt'].toPlainText().strip()
            
            if comment:
                output_lines.append(f"# {comment}")
            if prompt:
                output_lines.append(prompt)
        
        return "\n".join(output_lines)
    
    def save_to_file(self):
        output_text = self.get_output_text()
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Output", "", "Text Files (*.txt)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8', newline='\r\n') as f:
                    f.write(output_text)
            except Exception as e:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(self, "Error", f"Failed to save file: {str(e)}")