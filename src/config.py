"""HOSTrans 全局配置常量"""

# ── 游戏配置 ──────────────────────────────────────────
GAME_PROCESS_NAME = 'HeroesOfTheStorm_x64.exe'
GAME_WINDOW_TITLE = '《风暴英雄》'

# ── 快捷键 ────────────────────────────────────────────
HOTKEY_TRANSLATE = 'ctrl+p'       # 一键翻译输入框中文
HOTKEY_SWITCH_LANG = 'ctrl+l'     # 切换目标语言
HOTKEY_INIT = 'ctrl+1'            # 初始化内存定位
HOTKEY_VISION_TRANS = 'ctrl+2'    # 截图调用 LLM 理解并翻译
HOTKEY_RESHOW = 'ctrl+tab'        # 重新显示窗口

# ── 定时器间隔 (毫秒) ──────────────────────────────────
SCAN_INTERVAL_MS = 1000           # 内存扫描间隔
HIDE_DELAY_MS = 4500              # 自动隐藏窗口延迟

# ── 翻译相关 ──────────────────────────────────────────
TRANSLATOR_CONFIG_FILE = 'config.ini'
BAIDU_API_CONFIG_FILE = 'baiduAPI.txt'
BAIDU_API_HOST = 'api.fanyi.baidu.com'
BAIDU_API_PATH = '/api/trans/vip/translate'
DEFAULT_TRANSLATOR_PROVIDER = 'baidu'
DEFAULT_REQUEST_TIMEOUT = 5.0
DEFAULT_TARGET_LANG = 'kor'

# ── 内存扫描 ──────────────────────────────────────────
MEMORY_READ_MAX_LENGTH = 200      # 读取字符串最大字节数
INIT_SCAN_ROUNDS = 3              # 初始化时扫描轮数
ENCODING_CANDIDATES = ['utf-8', 'utf-16le', 'utf-16']

# ── UI ────────────────────────────────────────────────
WINDOW_TITLE = '风暴翻译'
MAX_MSG_COUNT = 10                # 消息列表最大条数
WINDOW_OPACITY_PERCENT = 40       # 初始窗口透明度 (0-100)

# ── 需要过滤的系统消息关键词 ──────────────────────────
SYSTEM_MSG_FILTERS = [
    '综合 한국어',
    '<c val="3184FF">[团队]:</c>',
    '浏览战利',
    '浏览收藏',
    '菜单',
]

# ── 模拟按键延迟 (秒) ─────────────────────────────────
KEYPRESS_DELAY = 0.4
RANDOM_MSG_LENGTH = 12
RANDOM_MSG_POST_DELAY = 1.0

# ── 截图与 LLM 视觉翻译 ───────────────────────────────
# 局内聊天内容区域相对于屏幕分辨率的硬编码偏移比例: (x_ratio, y_ratio, width_ratio, height_ratio)
CHAT_REGION_RATIOS = (0.01, 0.55, 0.35, 0.28)
DEFAULT_LLM_BASE_URL = 'https://api.openai.com/v1'
DEFAULT_LLM_MODEL = 'gpt-4o-mini'
DEFAULT_LLM_TIMEOUT = 15.0

LLM_VISION_PROMPT = (
    '你是一个《风暴英雄》游戏局内聊天翻译助手。请识别截图中的玩家聊天内容，忽略纯系统提示信息，'
    '并将非中文的玩家发言翻译为自然流畅的中文（结合MOBA游戏语境）。\n'
    '请严格输出合法的 JSON 对象，不要包含任何额外的解释文本或 Markdown 标记，格式如下：\n'
    '{\n'
    '  "messages": [\n'
    '    {"sender": "玩家或英雄名", "src": "原文内容", "dst": "中文译文"}\n'
    '  ]\n'
    '}\n'
    '如果截图中没有识别到任何有效的玩家发言，请返回：{"messages": []}'
)

