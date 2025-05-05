# main.py
import sys
import logging
from PyQt6.QtWidgets import QApplication
from ui_main import MainWindow

def main():
    # --- ロギング設定 ---
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.INFO, format=log_format) # コンソールにはINFO以上を表示

    # ファイルにも出力する場合 (DEBUGレベル以上)
    # file_handler = logging.FileHandler('app.log', encoding='utf-8')
    # file_handler.setLevel(logging.DEBUG)
    # file_handler.setFormatter(logging.Formatter(log_format))
    # logging.getLogger().addHandler(file_handler)
    # --- ここまで ---
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
