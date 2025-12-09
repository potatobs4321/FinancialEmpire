from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QApplication, QWidget
import sys

def main():
    app = QApplication(sys.argv)
    window = QWidget()
    window.setWindowTitle('最简单的 PyQt5 窗口')
    window.setGeometry(100, 100, 400, 300)  # x, y, width, height
    window.show()

    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
