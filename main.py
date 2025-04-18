# main.py
import sys
import logging
from PyQt6.QtWidgets import QApplication
from ui_main import MainWindow
# from modules.constants import LOG_FORMAT, LOG_LEVEL # LOG_LEVEL を直接指定するためコメントアウト

# LOG_LEVEL = logging.DEBUG # デバッグ用から
# LOG_LEVEL = logging.INFO # INFO レベルに戻す
LOG_LEVEL = logging.WARNING # INFO から WARNING に変更
LOG_FORMAT: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

def setup_logging():
    """アプリケーションの基本的なロギングを設定します。"""
    logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
    logger = logging.getLogger(__name__)
    logger.info(f"ロギングレベルを {logging.getLevelName(LOG_LEVEL)} に設定しました。") # INFO と表示されるはず

def main():
    setup_logging() # ロギング設定を呼び出し
    logger = logging.getLogger(__name__)
    logger.info("アプリケーションを開始します。")

    app = QApplication(sys.argv)
    try:
        main_window = MainWindow()
        main_window.show()
        exit_code = app.exec()
        logger.info(f"アプリケーションを終了します。終了コード: {exit_code}")
        sys.exit(exit_code)
    except Exception as e:
        logger.critical("予期せぬエラーによりアプリケーションがクラッシュしました。", exc_info=True)
        # ユーザーにエラーを通知するダイアログを表示することも検討
        sys.exit(1) # エラー終了を示す

if __name__ == "__main__":
    main()