from abc import ABC, abstractmethod
import configparser
import hashlib
import json
import os
import random
import time
import urllib.parse
import urllib.request
import uuid
from typing import Optional, Dict, Tuple

from config import (
    TRANSLATOR_CONFIG_FILE,
    BAIDU_API_CONFIG_FILE,
    DEFAULT_TRANSLATOR_PROVIDER,
    DEFAULT_REQUEST_TIMEOUT,
)


class BaseTranslator(ABC):
    """翻译器抽象基类"""

    LANG_MAP: Dict[str, str] = {}

    def __init__(self, timeout: float = DEFAULT_REQUEST_TIMEOUT):
        self.timeout = timeout

    def map_lang(self, lang: str) -> str:
        """将内部统一语种代码映射为当前平台对应的语种代码"""
        return self.LANG_MAP.get(lang, lang)

    @abstractmethod
    def trans(self, src_text: str, fromLang: str = 'auto', toLang: str = 'zh') -> str:
        """执行文本翻译，失败时统一返回 '翻译失败!'"""
        pass


class BaiduTranslator(BaseTranslator):
    """百度翻译通用文本 API 实现"""

    API_URL = 'https://fanyi-api.baidu.com/api/trans/vip/translate'
    LANG_MAP: Dict[str, str] = {
        'auto': 'auto',
        'zh': 'zh',
        'kor': 'kor',
        'ko': 'kor',
        'en': 'en',
    }

    def __init__(self, appid: str, secretkey: str, timeout: float = DEFAULT_REQUEST_TIMEOUT):
        super().__init__(timeout=timeout)
        self.appid = appid
        self.secretKey = secretkey

    def trans(self, src_text: str, fromLang: str = 'auto', toLang: str = 'zh') -> str:
        if not src_text:
            return ''
        from_lang = self.map_lang(fromLang)
        to_lang = self.map_lang(toLang)
        salt = str(random.randint(32768, 65536))
        sign_raw = self.appid + src_text + salt + self.secretKey
        sign = hashlib.md5(sign_raw.encode('utf-8')).hexdigest()

        params = urllib.parse.urlencode({
            'appid': self.appid,
            'q': src_text,
            'from': from_lang,
            'to': to_lang,
            'salt': salt,
            'sign': sign,
        })
        url = f"{self.API_URL}?{params}"

        try:
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                result_all = response.read().decode('utf-8')
                result = json.loads(result_all)
                if 'trans_result' in result and result['trans_result']:
                    return '\n'.join(item['dst'] for item in result['trans_result'])
                return '翻译失败!'
        except Exception:
            return '翻译失败!'


class YoudaoTranslator(BaseTranslator):
    """有道智云文本翻译 API v3 实现"""

    API_URL = 'https://openapi.youdao.com/api'
    LANG_MAP: Dict[str, str] = {
        'auto': 'auto',
        'zh': 'zh-CHS',
        'kor': 'ko',
        'ko': 'ko',
        'en': 'en',
    }

    def __init__(self, app_key: str, app_secret: str, timeout: float = DEFAULT_REQUEST_TIMEOUT):
        super().__init__(timeout=timeout)
        self.app_key = app_key
        self.app_secret = app_secret

    @staticmethod
    def _truncate(q: str) -> str:
        """有道 v3 签名所需的 input 截断规则"""
        size = len(q)
        if size <= 20:
            return q
        return q[:10] + str(size) + q[-10:]

    def trans(self, src_text: str, fromLang: str = 'auto', toLang: str = 'zh') -> str:
        if not src_text:
            return ''
        from_lang = self.map_lang(fromLang)
        to_lang = self.map_lang(toLang)
        curtime = str(int(time.time()))
        salt = str(uuid.uuid4())
        sign_raw = self.app_key + self._truncate(src_text) + salt + curtime + self.app_secret
        sign = hashlib.sha256(sign_raw.encode('utf-8')).hexdigest()

        data = urllib.parse.urlencode({
            'q': src_text,
            'from': from_lang,
            'to': to_lang,
            'appKey': self.app_key,
            'salt': salt,
            'sign': sign,
            'signType': 'v3',
            'curtime': curtime,
        }).encode('utf-8')

        try:
            req = urllib.request.Request(
                self.API_URL,
                data=data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                result_all = response.read().decode('utf-8')
                result = json.loads(result_all)
                if result.get('errorCode') == '0' and result.get('translation'):
                    return '\n'.join(result['translation'])
                return '翻译失败!'
        except Exception:
            return '翻译失败!'


class GoogleTranslator(BaseTranslator):
    """谷歌翻译实现（同时支持官方 Cloud API v2 与免费网页接口）"""

    FREE_API_URL = 'https://translate.googleapis.com/translate_a/single'
    CLOUD_API_URL = 'https://translation.googleapis.com/language/translate/v2'
    LANG_MAP: Dict[str, str] = {
        'auto': 'auto',
        'zh': 'zh-CN',
        'kor': 'ko',
        'ko': 'ko',
        'en': 'en',
    }

    def __init__(
        self,
        api_key: str = '',
        proxy: str = '',
        timeout: float = DEFAULT_REQUEST_TIMEOUT,
    ):
        super().__init__(timeout=timeout)
        self.api_key = api_key.strip()
        self.proxy = proxy.strip()
        self._opener = self._build_opener()

    def _build_opener(self) -> urllib.request.OpenerDirector:
        if self.proxy:
            proxy_handler = urllib.request.ProxyHandler({
                'http': self.proxy,
                'https': self.proxy,
            })
            return urllib.request.build_opener(proxy_handler)
        return urllib.request.build_opener()

    def trans(self, src_text: str, fromLang: str = 'auto', toLang: str = 'zh') -> str:
        if not src_text:
            return ''
        from_lang = self.map_lang(fromLang)
        to_lang = self.map_lang(toLang)

        try:
            if self.api_key:
                return self._trans_cloud_api(src_text, from_lang, to_lang)
            return self._trans_free_api(src_text, from_lang, to_lang)
        except Exception:
            return '翻译失败!'

    def _trans_cloud_api(self, src_text: str, from_lang: str, to_lang: str) -> str:
        """使用 Google Cloud Translation API v2 翻译"""
        payload: Dict[str, str] = {
            'q': src_text,
            'target': to_lang,
            'format': 'text',
            'key': self.api_key,
        }
        if from_lang and from_lang != 'auto':
            payload['source'] = from_lang

        data = urllib.parse.urlencode(payload).encode('utf-8')
        req = urllib.request.Request(
            self.CLOUD_API_URL,
            data=data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            method='POST',
        )
        with self._opener.open(req, timeout=self.timeout) as response:
            result = json.loads(response.read().decode('utf-8'))
            translations = result.get('data', {}).get('translations', [])
            if translations:
                return '\n'.join(item.get('translatedText', '') for item in translations)
            return '翻译失败!'

    def _trans_free_api(self, src_text: str, from_lang: str, to_lang: str) -> str:
        """使用 Google 免费网页端接口翻译"""
        params = urllib.parse.urlencode({
            'client': 'gtx',
            'sl': from_lang,
            'tl': to_lang,
            'dt': 't',
            'q': src_text,
        })
        url = f"{self.FREE_API_URL}?{params}"
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'},
            method='GET',
        )
        with self._opener.open(req, timeout=self.timeout) as response:
            result = json.loads(response.read().decode('utf-8'))
            if isinstance(result, list) and result and isinstance(result[0], list):
                translated = ''.join(seg[0] for seg in result[0] if seg and seg[0])
                if translated:
                    return translated
            return '翻译失败!'


def _load_legacy_baidu_credentials(base_dir: str) -> Optional[Tuple[str, str]]:
    """向下兼容：从旧版 baiduAPI.txt 读取 appid 和 secret_key"""
    api_file = os.path.join(base_dir, BAIDU_API_CONFIG_FILE)
    if os.path.exists(api_file):
        try:
            with open(api_file, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
                if len(lines) >= 2:
                    return lines[0], lines[1]
        except Exception:
            pass
    return None


def create_translator(config_path: Optional[str] = None) -> Optional[BaseTranslator]:
    """根据配置文件创建对应的翻译器实例"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if config_path is None:
        config_path = os.path.join(base_dir, TRANSLATOR_CONFIG_FILE)

    parser = configparser.ConfigParser()
    if os.path.exists(config_path):
        try:
            parser.read(config_path, encoding='utf-8')
        except Exception as e:
            print(f"读取配置文件 {config_path} 失败: {e}")

    provider = parser.get('general', 'provider', fallback=DEFAULT_TRANSLATOR_PROVIDER).strip().lower()
    try:
        timeout = float(parser.get('general', 'timeout', fallback=str(DEFAULT_REQUEST_TIMEOUT)))
    except ValueError:
        timeout = DEFAULT_REQUEST_TIMEOUT

    if provider == 'baidu':
        appid = parser.get('baidu', 'appid', fallback='').strip()
        secret_key = parser.get('baidu', 'secret_key', fallback='').strip()
        if not (appid and secret_key):
            legacy = _load_legacy_baidu_credentials(base_dir)
            if legacy:
                appid, secret_key = legacy
        if appid and secret_key:
            return BaiduTranslator(appid, secret_key, timeout=timeout)
        return None

    elif provider == 'youdao':
        app_key = parser.get('youdao', 'app_key', fallback='').strip()
        app_secret = parser.get('youdao', 'app_secret', fallback='').strip()
        if app_key and app_secret:
            return YoudaoTranslator(app_key, app_secret, timeout=timeout)
        return None

    elif provider == 'google':
        api_key = parser.get('google', 'api_key', fallback='').strip()
        proxy = parser.get('google', 'proxy', fallback='').strip()
        return GoogleTranslator(api_key=api_key, proxy=proxy, timeout=timeout)

    else:
        print(f"未知的翻译平台配置: {provider}")
        return None
