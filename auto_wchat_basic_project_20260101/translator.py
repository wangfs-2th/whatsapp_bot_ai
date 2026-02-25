"""
翻译模块 - 实现多语言翻译功能
"""
from deep_translator import GoogleTranslator
from typing import Optional
import logging
from config import TRANSLATION_ENABLED, DEFAULT_OUTGOING_LANGUAGE

logger = logging.getLogger(__name__)


class Translator:
    def __init__(self):
        self.translator = GoogleTranslator()
    
    def translate(self, text: str, target_lang: str = "zh", source_lang: str = "auto") -> Optional[str]:
        """翻译文本"""
        if not TRANSLATION_ENABLED or not text:
            return text
        
        try:
            lang_map = {
                "zh": "zh-CN", "zh-cn": "zh-CN", "chinese": "zh-CN",
                "en": "en", "english": "en",
                "ja": "ja", "japanese": "ja",
                "ru": "ru", "russian": "ru"
            }
            
            target = lang_map.get(target_lang.lower(), target_lang)
            
            if source_lang == "auto":
                translated = GoogleTranslator(source='auto', target=target).translate(text)
            else:
                source = lang_map.get(source_lang.lower(), source_lang)
                translated = GoogleTranslator(source=source, target=target).translate(text)
            
            logger.info(f"翻译成功: {text[:50]}... -> {translated[:50]}...")
            return translated
        
        except Exception as e:
            logger.error(f"翻译失败: {e}")
            return text
    
    def translate_to_chinese(self, text: str) -> Optional[str]:
        """将文本翻译成中文"""
        return self.translate(text, target_lang="zh")
    
    def translate_to_english(self, text: str) -> Optional[str]:
        """将文本翻译成英文"""
        return self.translate(text, target_lang="en")
    
    def translate_to_japanese(self, text: str) -> Optional[str]:
        """将文本翻译成日语"""
        return self.translate(text, target_lang="ja")
    
    def translate_to_russian(self, text: str) -> Optional[str]:
        """将文本翻译成俄语"""
        return self.translate(text, target_lang="ru")
    
    def translate_outgoing(self, text: str, lang: str = None) -> Optional[str]:
        """翻译要发送的消息"""
        if not lang:
            lang = DEFAULT_OUTGOING_LANGUAGE
        
        return self.translate(text, target_lang=lang, source_lang="zh")








