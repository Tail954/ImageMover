# modules/constants.py
"""
アプリケーション全体で使用される定数を定義します。
"""
from enum import Enum, auto

# --- 設定関連 ---
CONFIG_FILE_NAME: str = "last_value.json"

# 設定キー
class ConfigKeys:
    FOLDER: str = "folder"
    THUMBNAIL_COLUMNS: str = "thumbnail_columns"
    CACHE_SIZE: str = "cache_size"
    SORT_ORDER: str = "sort_order"
    PREVIEW_MODE: str = "preview_mode"
    OUTPUT_FORMAT: str = "output_format"

# デフォルト設定値
DEFAULT_CONFIG = {
    ConfigKeys.FOLDER: "",
    ConfigKeys.THUMBNAIL_COLUMNS: 5,
    ConfigKeys.CACHE_SIZE: 1000,
    ConfigKeys.SORT_ORDER: "filename_asc", # SortOrder Enum を使う方がより良いが、文字列で統一
    ConfigKeys.PREVIEW_MODE: "seamless",   # PreviewMode Enum を使う方がより良いが、文字列で統一
    ConfigKeys.OUTPUT_FORMAT: "separate_lines" # OutputFormat Enum を使う方がより良いが、文字列で統一
}

# --- UI関連 ---
DEFAULT_THUMBNAIL_COLUMNS: int = 5
MIN_THUMBNAIL_COLUMNS: int = 1
MAX_THUMBNAIL_COLUMNS: int = 20
DEFAULT_THUMBNAIL_SIZE: int = 200
PREVIEW_THUMBNAIL_SIZE: int = 250 # WCCreatorDialog での使用サイズ
OUTPUT_PREVIEW_THUMBNAIL_SIZE: int = 150 # OutputDialog での使用サイズ
IMAGE_DIALOG_MIN_WIDTH: int = 600
IMAGE_DIALOG_MIN_HEIGHT: int = 500
METADATA_DIALOG_MIN_WIDTH: int = 400
METADATA_DIALOG_MIN_HEIGHT: int = 600
WC_CREATOR_DIALOG_WIDTH: int = 900
WC_CREATOR_DIALOG_HEIGHT: int = 600
OUTPUT_DIALOG_WIDTH: int = 1000
OUTPUT_DIALOG_HEIGHT: int = 700

# ソート順識別子 (文字列で管理)
SORT_FILENAME_ASC: str = "filename_asc"
SORT_FILENAME_DESC: str = "filename_desc"
SORT_DATE_ASC: str = "date_asc"
SORT_DATE_DESC: str = "date_desc"

# プレビューモード識別子 (文字列で管理)
PREVIEW_MODE_SEAMLESS: str = "seamless"
PREVIEW_MODE_WHEEL: str = "wheel"

# 出力フォーマット識別子 (文字列で管理)
OUTPUT_FORMAT_SEPARATE: str = "separate_lines"
OUTPUT_FORMAT_INLINE: str = "inline_format"

# --- メタデータ関連 ---
class MetadataKeys:
    POSITIVE: str = "positive_prompt"
    NEGATIVE: str = "negative_prompt"
    INFO: str = "generation_info"
    PARAMS: str = "parameters"
    EXIF: str = "exif"
    ERROR: str = "error"

# --- 画像ファイル関連 ---
VALID_IMAGE_EXTENSIONS: set[str] = {'.png', '.jpeg', '.jpg', '.webp'}

# --- スレッド関連 ---
IMAGE_LOADER_MAX_WORKERS: int = 4

# --- ログ関連 ---
LOG_FORMAT: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_LEVEL = "INFO" # 必要に応じて DEBUG, WARNING, ERROR に変更

# --- その他 ---
THUMBNAIL_BORDER_SELECTED: str = "border: 3px solid orange;"
THUMBNAIL_ORDER_LABEL_STYLE: str = "color: white; background-color: black;"