import sys
import cv2
import numpy as np
import pyautogui
import threading
import time
import win32gui
import win32con
import keyboard
import os
import logging
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *


class ScreenCaptureArea(QWidget):
    areaSelected = pyqtSignal(QRect)  # 시그널 추가

    def __init__(self):
        super().__init__()
        # 전체 화면 크기 가져오기
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)

        # 윈도우 설정
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)

        # 변수 초기화
        self.start_pos = None
        self.current_pos = None
        self.is_drawing = False

        # 화면을 어둡게 만들기 위한 배경
        self.background = QPixmap(screen.size())
        self.background.fill(QColor(0, 0, 0, 100))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.background)

        if self.is_drawing and self.start_pos and self.current_pos:
            mask = QRegion(self.rect()) - QRegion(self.selection_rect())
            painter.setClipRegion(mask)
            painter.drawPixmap(self.rect(), self.background)

            # 선택 영역 그리기
            painter.setClipRect(self.rect())
            pen = QPen(Qt.red, 2)
            painter.setPen(pen)
            painter.drawRect(self.selection_rect())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = event.pos()
            self.current_pos = event.pos()
            self.is_drawing = True

    def mouseMoveEvent(self, event):
        if self.is_drawing:
            self.current_pos = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_drawing:
            self.is_drawing = False
            if self.start_pos and self.current_pos:
                self.areaSelected.emit(self.selection_rect())
            self.close()

    def selection_rect(self):
        if self.start_pos and self.current_pos:
            return QRect(
                min(self.start_pos.x(), self.current_pos.x()),
                min(self.start_pos.y(), self.current_pos.y()),
                abs(self.start_pos.x() - self.current_pos.x()),
                abs(self.start_pos.y() - self.current_pos.y())
            )
        return QRect()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()

class AutoClickerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.killswitch_activated = False
        self.images = []
        self.running = False
        self.selected_area = None
        self.initUI()
        self.setup_logging()

    def setup_logging(self):
        logging.basicConfig(filename='clicker.log', level=logging.INFO,
                            format='%(asctime)s - %(levelname)s: %(message)s')

    def initUI(self):
        # 메인 윈도우 설정
        self.setWindowTitle('Auto Clicker')
        self.setGeometry(100, 100, 600, 400)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
            }
            QPushButton {
                background-color: #4a4a4a;
                color: white;
                border: none;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
            QLabel {
                color: white;
            }
            QListWidget {
                background-color: #3b3b3b;
                color: white;
                border: 1px solid #555555;
            }
        """)

        # 중앙 위젯 생성
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # 이미지 목록 위젯
        self.image_list = QListWidget()
        layout.addWidget(QLabel('등록된 이미지:'))
        layout.addWidget(self.image_list)

        # 버튼 그룹
        button_layout = QHBoxLayout()

        # 이미지 추가 버튼
        add_btn = QPushButton('이미지 추가')
        add_btn.clicked.connect(self.add_image)
        button_layout.addWidget(add_btn)

        # 이미지 제거 버튼
        remove_btn = QPushButton('이미지 제거')
        remove_btn.clicked.connect(self.remove_image)
        button_layout.addWidget(remove_btn)

        layout.addLayout(button_layout)

        # 설정 그룹
        settings_group = QGroupBox('설정')
        settings_layout = QFormLayout()

        # 임계값 설정
        self.threshold_input = QDoubleSpinBox()
        self.threshold_input.setRange(0.1, 1.0)
        self.threshold_input.setValue(0.8)
        self.threshold_input.setSingleStep(0.1)
        settings_layout.addRow('임계값:', self.threshold_input)

        # 클릭 지연 설정
        self.delay_input = QDoubleSpinBox()
        self.delay_input.setRange(0.01, 5.0)
        self.delay_input.setValue(0.01)
        self.delay_input.setSingleStep(0.01)
        settings_layout.addRow('클릭 지연(초):', self.delay_input)

        # 킬스위치 키 설정
        self.killswitch_input = QLineEdit('q')
        settings_layout.addRow('정지 키:', self.killswitch_input)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # 영역 선택 버튼
        area_select_btn = QPushButton('영역 선택')
        area_select_btn.clicked.connect(self.select_area)
        layout.addWidget(area_select_btn)

        # 선택된 영역 표시 레이블
        self.area_label = QLabel('선택된 영역: 없음')
        layout.addWidget(self.area_label)

        # 시작/정지 버튼
        self.start_stop_btn = QPushButton('시작')
        self.start_stop_btn.clicked.connect(self.toggle_clicking)
        layout.addWidget(self.start_stop_btn)

        # 상태 표시줄
        self.status_label = QLabel('대기 중')
        layout.addWidget(self.status_label)

    def select_area(self):
        self.hide()  # 메인 윈도우 숨기기
        time.sleep(0.2)  # 화면 전환을 위한 짧은 대기

        screen_capture = ScreenCaptureArea()
        screen_capture.areaSelected.connect(self.area_selected)
        screen_capture.show()

        # 영역 선택이 완료될 때까지 대기
        while screen_capture.isVisible():
            QApplication.processEvents()

        self.show()  # 메인 윈도우 다시 표시

    def area_selected(self, rect):
        if rect.isValid():
            self.selected_area = (
                rect.x(),
                rect.y(),
                rect.width(),
                rect.height()
            )
            self.area_label.setText(f'선택된 영역: {self.selected_area}')
        else:
            self.selected_area = None
            self.area_label.setText('선택된 영역: 없음')

    def add_image(self):
        files, _ = QFileDialog.getOpenFileNames(self, "이미지 선택", "",
                                                "Image files (*.png *.jpg *.jpeg *.bmp)")
        for file in files:
            if file not in self.images:
                self.images.append(file)
                self.image_list.addItem(os.path.basename(file))

    def remove_image(self):
        current_row = self.image_list.currentRow()
        if current_row >= 0:
            del self.images[current_row]
            self.image_list.takeItem(current_row)

    def toggle_clicking(self):
        if not self.running:
            self.start_clicking()
        else:
            self.stop_clicking()

    def start_clicking(self):
        if not self.images:
            QMessageBox.warning(self, '경고', '이미지를 먼저 추가해주세요.')
            return

        self.running = True
        self.killswitch_activated = False
        self.start_stop_btn.setText('정지')
        self.status_label.setText('실행 중...')

        # 클리커 스레드 시작
        self.clicker_thread = threading.Thread(target=self.search_and_click)
        self.clicker_thread.start()

        # 킬스위치 모니터링 스레드 시작
        self.killswitch_thread = threading.Thread(target=self.monitor_killswitch)
        self.killswitch_thread.start()

    def stop_clicking(self):
        self.killswitch_activated = True
        self.running = False
        self.start_stop_btn.setText('시작')
        self.status_label.setText('정지됨')

    def monitor_killswitch(self):
        killswitch_key = self.killswitch_input.text()
        while self.running:
            if keyboard.is_pressed(killswitch_key):
                self.killswitch_activated = True
                self.running = False
                break
            time.sleep(0.1)

    def search_and_click(self):
        method = cv2.TM_CCOEFF_NORMED
        threshold = self.threshold_input.value()
        click_delay = self.delay_input.value()

        while self.running and not self.killswitch_activated:
            if self.selected_area:
                # 선택된 영역만 스크린샷 촬영
                screenshot = pyautogui.screenshot(region=self.selected_area)
            else:
                # 전체 화면 스크린샷
                screenshot = pyautogui.screenshot()

            screen_np = np.array(screenshot)
            screen_gray = cv2.cvtColor(screen_np, cv2.COLOR_RGB2GRAY)

            for image_path in self.images:
                if not self.running or self.killswitch_activated:
                    break

                template = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
                result = cv2.matchTemplate(screen_gray, template, method)
                loc = np.where(result >= threshold)

                for pt in zip(*loc[::-1]):
                    if not self.running or self.killswitch_activated:
                        break

                    # 선택된 영역이 있는 경우 좌표 조정
                    if self.selected_area:
                        x = pt[0] + template.shape[1] // 2 + self.selected_area[0]
                        y = pt[1] + template.shape[0] // 2 + self.selected_area[1]
                    else:
                        x = pt[0] + template.shape[1] // 2
                        y = pt[1] + template.shape[0] // 2

                    pyautogui.click(x, y)
                    logging.info(f"Clicked on {image_path} at ({x}, {y})")
                    time.sleep(click_delay)

        self.status_label.setText('대기 중')
        self.start_stop_btn.setText('시작')


def main():
    app = QApplication(sys.argv)
    ex = AutoClickerGUI()
    ex.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
