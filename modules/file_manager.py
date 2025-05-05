# g:\vscodeGit\modules\file_manager.py
import os
import shutil
import re
from pathlib import Path

try:
    from send2trash import send2trash
    SEND2TRASH_AVAILABLE = True
except ImportError:
    SEND2TRASH_AVAILABLE = False
    print("Warning: send2trash library not found. Empty folder removal will delete permanently.")

class FileManager:
    """ファイル操作（移動、コピー、空フォルダ削除）を担当するクラス"""

    def move_files(self, source_paths, destination_folder):
        """
        指定されたファイルを宛先フォルダに移動する。
        重複する場合はリネームする。

        Args:
            source_paths (list[str]): 移動元のファイルパスのリスト。
            destination_folder (str): 移動先のフォルダパス。

        Returns:
            dict: 操作結果 {'moved_count': int, 'renamed_files': list[str], 'errors': list[str]}
        """
        moved_count = 0
        renamed_files = []
        errors = []

        if not os.path.isdir(destination_folder):
            errors.append(f"Destination folder does not exist: {destination_folder}")
            return {'moved_count': 0, 'renamed_files': [], 'errors': errors}

        for src_path in source_paths:
            if not os.path.exists(src_path):
                errors.append(f"Source file not found: {os.path.basename(src_path)}")
                continue

            base_name, ext = os.path.splitext(os.path.basename(src_path))
            dest_path = os.path.join(destination_folder, base_name + ext)
            counter = 1
            original_dest_path = dest_path
            while os.path.exists(dest_path):
                dest_path = os.path.join(destination_folder, f"{base_name}_{counter}{ext}")
                counter += 1

            try:
                shutil.move(src_path, dest_path)
                moved_count += 1
                if dest_path != original_dest_path:
                    renamed_files.append(os.path.basename(dest_path))
            except Exception as e:
                error_msg = f"Error moving {os.path.basename(src_path)}: {e}"
                print(error_msg)
                errors.append(error_msg)

        return {'moved_count': moved_count, 'renamed_files': renamed_files, 'errors': errors}

    def copy_files(self, ordered_source_paths, destination_folder):
        """
        指定されたファイルを指定された順序で宛先フォルダにコピーする。
        コピー先のファイル名は連番プレフィックス付きになる。

        Args:
            ordered_source_paths (list[str]): コピー元のファイルパスのリスト（選択順）。
            destination_folder (str): コピー先のフォルダパス。

        Returns:
            dict: 操作結果 {'copied_count': int, 'errors': list[str]}
        """
        copied_count = 0
        errors = []

        if not os.path.isdir(destination_folder):
            errors.append(f"Destination folder does not exist: {destination_folder}")
            return {'copied_count': 0, 'errors': errors}

        try:
            existing_files = [f for f in os.listdir(destination_folder) if os.path.isfile(os.path.join(destination_folder, f))]
            existing_numbers = []
            for f in existing_files:
                match = re.match(r'^(\d+)_', f)
                if match:
                    try:
                        num = int(match.group(1))
                        existing_numbers.append(num)
                    except ValueError:
                        continue
            next_number = max(existing_numbers, default=0) + 1
        except Exception as e:
            errors.append(f"Could not read destination folder contents: {e}")
            return {'copied_count': 0, 'errors': errors}

        for src_path in ordered_source_paths:
            if not os.path.exists(src_path):
                errors.append(f"Source file not found: {os.path.basename(src_path)}")
                continue

            base_name = os.path.basename(src_path)
            new_filename = f"{next_number:03}_{base_name}"
            dest_path = os.path.join(destination_folder, new_filename)

            counter = 1
            original_dest_path = dest_path
            while os.path.exists(dest_path):
                 name, ext = os.path.splitext(original_dest_path)
                 dest_path = f"{name}_{counter}{ext}"
                 counter += 1

            try:
                shutil.copy2(src_path, dest_path) # メタデータもコピー
                copied_count += 1
                next_number += 1
            except Exception as e:
                error_msg = f"Error copying {os.path.basename(src_path)}: {e}"
                print(error_msg)
                errors.append(error_msg)

        return {'copied_count': copied_count, 'errors': errors}

    def find_empty_folders(self, folder):
        """指定されたフォルダ以下の空フォルダを検索する"""
        empty_folders = []
        for root, dirs, files in os.walk(folder, topdown=False):
            normalized_root = os.path.normpath(root.replace('\\\\?\\', ''))
            if not os.listdir(normalized_root):
                empty_folders.append(normalized_root)
        return empty_folders

    def remove_folders_to_trash(self, folder_paths):
        """指定されたフォルダをゴミ箱に移動する"""
        if not SEND2TRASH_AVAILABLE:
            return {'deleted_count': 0, 'errors': ["send2trash library is not available."]}

        deleted_count = 0
        errors = []
        for dir_path in folder_paths:
            try:
                send2trash(dir_path)
                print(f"Moved to trash: {dir_path}")
                deleted_count += 1
            except Exception as e:
                error_msg = f"Failed to move to trash {dir_path}: {e}"
                print(error_msg)
                errors.append(error_msg)
        return {'deleted_count': deleted_count, 'errors': errors}