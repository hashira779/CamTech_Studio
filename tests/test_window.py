"""Quick test: does a PySide6 window appear on your screen?"""
import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QPushButton, QVBoxLayout, QWidget
from PySide6.QtCore import Qt

app = QApplication(sys.argv)

win = QMainWindow()
win.setWindowTitle("TEST - Can you see this window?")
win.resize(600, 400)

central = QWidget()
layout = QVBoxLayout(central)
layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

label = QLabel("✅ PySide6 Window Works!")
label.setStyleSheet("font-size: 32px; font-weight: bold; color: #00ff88;")
layout.addWidget(label, alignment=Qt.AlignmentFlag.AlignCenter)

label2 = QLabel("If you see this, Qt 6 is working.\nClose this window to continue.")
label2.setStyleSheet("font-size: 16px; color: #cccccc;")
label2.setAlignment(Qt.AlignmentFlag.AlignCenter)
layout.addWidget(label2, alignment=Qt.AlignmentFlag.AlignCenter)

btn = QPushButton("Close")
btn.setFixedSize(120, 40)
btn.clicked.connect(win.close)
layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

win.setCentralWidget(central)
win.setStyleSheet("QMainWindow { background-color: #1a1a2e; }")

win.show()
win.raise_()
win.activateWindow()
print("[TEST] Window shown", flush=True)

sys.exit(app.exec())
