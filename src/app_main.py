from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout,
                             QWidget, QLabel, QPushButton, QListWidget)
from PyQt5.QtGui import QColor, QPainter, QBrush, QPen
from PyQt5.QtCore import QObject, pyqtSignal, Qt, QTimer, QRunnable, QThreadPool
import pyautogui
import time
import sys
from collections import deque
from config import CHAT_REGION_RATIOS, HOTKEY_VISION_TRANS
from translator import create_translator, BaseTranslator, create_llm_translator, LLMVisionTranslator
from utils import window_exists, contains_korean, generate_random_string, capture_chat_region_base64
from memory_utils import read_string, get_process_id, get_process_handle, scan_memory_bytes, CloseHandle
import keyboard
from qss_style import list_widget_style, main_style, title_label_style

GAME_APP_NAME = 'HeroesOfTheStorm_x64.exe'


class GlobalHotkey(QObject):
    triggered = pyqtSignal()

    def __init__(self, hotkey):
        super().__init__()
        self.hotkey = hotkey
        keyboard.add_hotkey(hotkey, self._on_trigger)

    def _on_trigger(self):
        self.triggered.emit()

    def unregister(self):
        """显式注销快捷键，避免依赖 __del__"""
        try:
            keyboard.remove_hotkey(self.hotkey)
        except Exception:
            pass

    def __del__(self):
        self.unregister()


class HotKey(object):
    def __init__(self, key):
        self.key = key

    def run(self):
        # 区分元组和字符串：元组需要解包为多个参数
        if isinstance(self.key, (tuple, list)):
            pyautogui.hotkey(*self.key)
        else:
            pyautogui.hotkey(self.key)
        time.sleep(0.4)


class TranslationSignals(QObject):
    """异步翻译任务信号载体"""
    finished = pyqtSignal(str, str)


class TranslationTask(QRunnable):
    """基于 Qt 线程池的异步翻译工作任务"""

    def __init__(self, translator: BaseTranslator, src_text: str, from_lang: str = 'auto', to_lang: str = 'zh'):
        super().__init__()
        self.translator = translator
        self.src_text = src_text
        self.from_lang = from_lang
        self.to_lang = to_lang
        self.signals = TranslationSignals()

    def run(self):
        dst_text = self.translator.trans(self.src_text, fromLang=self.from_lang, toLang=self.to_lang)
        self.signals.finished.emit(self.src_text, dst_text)


class VisionTranslationSignals(QObject):
    """异步截图 LLM 翻译任务信号载体"""
    finished = pyqtSignal(list, str)


class VisionTranslationTask(QRunnable):
    """基于 Qt 线程池的异步截图 LLM 理解翻译工作任务"""

    def __init__(self, llm_translator: LLMVisionTranslator, image_base64: str):
        super().__init__()
        self.llm_translator = llm_translator
        self.image_base64 = image_base64
        self.signals = VisionTranslationSignals()

    def run(self):
        try:
            messages = self.llm_translator.trans_image(self.image_base64)
            self.signals.finished.emit(messages, '')
        except Exception as e:
            self.signals.finished.emit([], str(e))



class TransparentWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.init_ui()
        self.hotkeys = []  # 保存快捷键对象引用，防止被GC回收
        self.register_hotkey()
        self.init_timer()

        self.my_last_msg = ''
        self.address = None
        self.pid = None
        self.init_state = False
        self.hided = False
        self.msg_list = deque(maxlen=100)  # 限制最大长度，防止无限增长
        self.last_status_msg = ''  # 用于状态消息去重

        self.old_pos = None
        self.handle = None
        self.encoding_format = 'utf-8'
        self.thread_pool = QThreadPool.globalInstance()
        self._active_tasks = set()  # 保存执行中的异步任务引用，防止提前被GC回收
        self.is_translating_input = False  # 防止输入框翻译重入
        self.is_translating_vision = False  # 防止截图LLM翻译重入
        self.llm_trans = None
        self.get_translator()
        self.target_lan = 'kor'

    def init_ui(self):
        # 设置窗口属性
        self.setWindowFlags(
            Qt.FramelessWindowHint |  # 无边框
            Qt.WindowStaysOnTopHint  # 置顶
        )
        self.setAttribute(Qt.WA_TranslucentBackground)  # 透明背景
        self.opacity = 40

        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)

        layout = QVBoxLayout()
        self.main_widget.setLayout(layout)

        self.title_label = QLabel("风暴翻译")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet(title_label_style)

        # 添加QListWidget
        self.list_widget = QListWidget()
        self.list_widget.setWordWrap(True)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setStyleSheet(list_widget_style)

        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.close)

        layout.addWidget(self.title_label)
        layout.addWidget(self.list_widget)
        layout.addWidget(self.close_btn)
        self.setStyleSheet(main_style)
        self.resize(300, 400)
        self.setGeometry(150, 150, 300, 400)

    def init_timer(self):
        self.scan_timer = QTimer(self)
        self.scan_timer.timeout.connect(self.scan_memory)
        self.scan_timer.start(1000)

        # 使用 singleShot 模式，避免隐藏后仍重复触发
        self.hide_win_timer = QTimer(self)
        self.hide_win_timer.setSingleShot(True)
        self.hide_win_timer.timeout.connect(self.hide_win)
        self.hide_win_timer.start(4500)

    def get_translator(self):
        self.trans = create_translator()
        if self.trans is None:
            print("警告: 翻译器初始化失败，请检查 config.ini 或 baiduAPI.txt 配置")
        self.llm_trans = create_llm_translator()

    def hide_win(self):
        if self.hided:
            return
        if self.init_state:
            self.hided = True
            self.hide()

    def reshow(self):
        if not self.hided:
            return
        self.hided = False
        self.show()
        self.hide_win_timer.start(4500)

    def register_hotkey(self):
        # 将快捷键对象存储到列表中，防止被垃圾回收
        hk_trans = GlobalHotkey("ctrl+p")
        hk_trans.triggered.connect(self.auto_trans)
        self.hotkeys.append(hk_trans)

        hk_switch = GlobalHotkey("ctrl+l")
        hk_switch.triggered.connect(self.switch_lan)
        self.hotkeys.append(hk_switch)

        hk_locate = GlobalHotkey("ctrl+1")
        hk_locate.triggered.connect(self.locate_memory_region)
        self.hotkeys.append(hk_locate)

        hk_vision = GlobalHotkey(HOTKEY_VISION_TRANS)
        hk_vision.triggered.connect(self.vision_trans)
        self.hotkeys.append(hk_vision)

        hk_reshow = GlobalHotkey("ctrl+tab")
        hk_reshow.triggered.connect(self.reshow)
        self.hotkeys.append(hk_reshow)

    def set_opacity(self, value):
        self.opacity = value
        self.setWindowOpacity(value / 100)
        self.update()  # 触发重绘

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 设置背景颜色和透明度
        color = QColor(100, 100, 200, int(255 * (self.opacity / 100)))
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(Qt.NoPen))

        # 绘制圆角矩形
        rect = self.rect()
        painter.drawRoundedRect(rect, 10, 10)

    def switch_lan(self):
        if self.target_lan == 'kor':
            self.target_lan = 'en'
            lan = '英语'
        else:
            self.target_lan = 'kor'
            lan = '韩语'
        self.add_msg(f'翻译模式:中译{lan}')

    def add_msg(self, msg):
        self.list_widget.addItem(msg)
        if self.list_widget.count() > 10:
            self.list_widget.takeItem(0)
        self.list_widget.scrollToBottom()

    def add_status_msg(self, msg):
        """添加状态消息（自动去重，避免刷屏）"""
        if msg == self.last_status_msg:
            return
        self.last_status_msg = msg
        self.add_msg(msg)

    def send_random_chat_msg(self):
        enter = HotKey('enter')
        random_chat_msg = generate_random_string(12)
        enter.run()
        for char in random_chat_msg:
            hk = HotKey(char)
            hk.run()
        enter.run()
        time.sleep(1)
        return random_chat_msg

    def get_process_handle(self):
        if self.pid is None:
            self.pid = get_process_id(GAME_APP_NAME)
        if not self.handle:
            self.handle = get_process_handle(self.pid)
        self.add_msg('PID:{} Handle:{}'.format(self.pid, self.handle))

    def locate_memory_region(self):
        self.get_process_handle()
        encoding_formats = ['utf-8', 'utf-16le', 'utf-16']
        self.add_msg('初始化中，不要操作键鼠')
        for encoding_format in encoding_formats:
            candidate_address_list = []
            for _ in range(3):
                random_chat_msg = self.send_random_chat_msg()

                candidate_address = scan_memory_bytes(self.handle,
                                                      random_chat_msg.encode(encoding=encoding_format))  # 粗定位
                candidate_address_list.append(candidate_address)
            candidate_address_list = [set(v) for v in candidate_address_list]
            candidate_address = candidate_address_list[0] & candidate_address_list[1] & candidate_address_list[2]
            candidate_address = list(candidate_address)
            if len(candidate_address) == 1:
                self.address = candidate_address[0]
                self.encoding_format = encoding_format
                break
        if self.address is not None:
            self.hide_win_timer.start(4500)
            self.init_state = True
            self.add_msg('初始化成功, 监听地址{}'.format(hex(self.address)))
        else:
            self.add_msg('初始化失败，请尝试重启游戏和插件')

    def auto_trans(self):
        if not window_exists("《风暴英雄》"):
            return
        if self.trans is None:
            self.add_msg('翻译器未初始化，请检查 config.ini 配置')
            return
        if self.is_translating_input:
            return
        self.hide_win_timer.stop()

        # 保存剪贴板原始内容
        clipboard = QApplication.clipboard()
        original_clipboard = clipboard.text()

        select_all = HotKey(('ctrl', 'a'))
        copy = HotKey(('ctrl', 'c'))
        for _ in range(2):
            select_all.run()
            time.sleep(0.01)
            copy.run()
            time.sleep(0.01)
        chinese_text = clipboard.text()
        if not chinese_text:
            # 恢复剪贴板
            clipboard.setText(original_clipboard)
            return

        self.is_translating_input = True
        task = TranslationTask(self.trans, chinese_text, from_lang='zh', to_lang=self.target_lan)
        self._active_tasks.add(task)
        task.signals.finished.connect(
            lambda src, dst, orig=original_clipboard, t=task: self._on_auto_trans_finished(dst, orig, t)
        )
        self.thread_pool.start(task)

    def _on_auto_trans_finished(self, foreign_text: str, original_clipboard: str, task: TranslationTask):
        self._active_tasks.discard(task)
        self.is_translating_input = False
        clipboard = QApplication.clipboard()
        if not foreign_text or '翻译失败' in foreign_text:
            clipboard.setText(original_clipboard)
            self.add_msg('输入翻译失败，请检查网络或 API 配置')
            return

        clipboard.setText(foreign_text)
        self.my_last_msg = foreign_text
        select_all = HotKey(('ctrl', 'a'))
        paste = HotKey(('ctrl', 'v'))
        for _ in range(2):
            select_all.run()
            paste.run()
            time.sleep(0.01)

        # 恢复剪贴板原始内容
        clipboard.setText(original_clipboard)

    def scan_memory(self):
        if not window_exists("《风暴英雄》"):
            self.add_status_msg('游戏未启动')
            self.reshow()
            return
        if not self.init_state:
            return
        if self.trans is None:
            return
        # 清除状态消息去重标记（游戏已启动，下次未启动时应再次提示）
        self.last_status_msg = ''

        text = read_string(self.handle, self.address, 200, self.encoding_format)
        if text is None or len(text) == 0:
            return
        sys_msgs = ['综合 한국어', '<c val="3184FF">[团队]:</c>', '浏览战利', '浏览收藏', '菜单']
        for sys_msg in sys_msgs:
            if sys_msg in text:
                return
        if contains_korean(text) and text != self.my_last_msg:
            if text in self.msg_list:
                return
            self.msg_list.append(text)
            task = TranslationTask(self.trans, text, from_lang='auto', to_lang='zh')
            self._active_tasks.add(task)
            task.signals.finished.connect(
                lambda src, dst, t=task: self._on_scan_trans_finished(src, dst, t)
            )
            self.thread_pool.start(task)

    def _on_scan_trans_finished(self, src_text: str, ch_text: str, task: TranslationTask):
        self._active_tasks.discard(task)
        if not ch_text or '翻译失败' in ch_text:
            if src_text in self.msg_list:
                self.msg_list.remove(src_text)
            return
        self.add_msg(src_text)
        self.add_msg(ch_text)
        self.reshow()
        self.hide_win_timer.start(4500)  # 重置隐藏窗体倒计时

    def vision_trans(self):
        """快捷键触发：截取局内聊天区域并调用 LLM 理解与翻译"""
        if not window_exists("《风暴英雄》"):
            return
        if self.llm_trans is None:
            self.add_msg('LLM 未配置，请检查 config.ini 的 [llm] 配置')
            self.reshow()
            self.hide_win_timer.start(4500)
            return
        if self.is_translating_vision:
            return

        try:
            image_b64 = capture_chat_region_base64(CHAT_REGION_RATIOS)
        except Exception:
            self.add_msg('局部屏幕截图失败')
            self.reshow()
            self.hide_win_timer.start(4500)
            return

        self.is_translating_vision = True
        task = VisionTranslationTask(self.llm_trans, image_b64)
        self._active_tasks.add(task)
        task.signals.finished.connect(
            lambda msgs, err, t=task: self._on_vision_trans_finished(msgs, err, t)
        )
        self.thread_pool.start(task)

    def _on_vision_trans_finished(self, messages: list, error_msg: str, task: VisionTranslationTask):
        self._active_tasks.discard(task)
        self.is_translating_vision = False

        if error_msg:
            self.add_msg('截图翻译失败，请检查 LLM 配置或网络')
            self.reshow()
            self.hide_win_timer.start(4500)
            return

        if not messages:
            self.add_msg('未识别到局内聊天内容')
            self.reshow()
            self.hide_win_timer.start(4500)
            return

        for item in messages:
            sender = item.get('sender', '')
            src = item.get('src', '')
            dst = item.get('dst', '')
            if sender:
                formatted = f'[{sender}] {src} -> {dst}'
            else:
                formatted = f'{src} -> {dst}'
            if formatted not in self.msg_list:
                self.msg_list.append(formatted)
                self.add_msg(formatted)

        self.reshow()
        self.hide_win_timer.start(4500)


    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.old_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        if self.old_pos:
            delta = event.globalPos() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPos()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.old_pos = None

    def closeEvent(self, event):
        # 停止所有定时器
        self.scan_timer.stop()
        self.hide_win_timer.stop()
        # 注销所有快捷键
        for hk in self.hotkeys:
            hk.unregister()
        self.hotkeys.clear()
        # 关闭进程句柄
        if self.handle is not None:
            CloseHandle(self.handle)
            self.handle = None
        # 接受关闭事件（而非调用 self.close() 导致无限递归）
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TransparentWindow()
    window.show()
    sys.exit(app.exec_())
