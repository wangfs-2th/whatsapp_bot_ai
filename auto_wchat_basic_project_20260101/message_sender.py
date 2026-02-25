"""
消息发送模块 - 实现定时发送、批量发送、条件触发发送等功能
"""
import time
import logging
import random
from typing import List, Dict, Optional, Callable
from datetime import datetime, timedelta
import schedule
from threading import Thread
from config import MAX_MESSAGES_PER_HOUR, MIN_REPLY_INTERVAL, MAX_RECIPIENTS_PER_BATCH, BATCH_DELAY_BETWEEN
from database import Database
from translator import Translator

logger = logging.getLogger(__name__)


class MessageSender:
    def __init__(self, whatsapp_client, database: Database):
        self.client = whatsapp_client
        self.db = database
        self.translator = Translator()
        self.scheduler_running = False
        self.scheduler_thread = None
        self.max_recipients_per_batch = MAX_RECIPIENTS_PER_BATCH
        self.batch_delay_between = BATCH_DELAY_BETWEEN
    
    def send_message(self, chat_id: str, message: str, delay: float = None, 
                    translate: bool = True, target_lang: str = None) -> bool:
        """发送单条消息"""
        if not self._check_rate_limit():
            logger.warning("已达到每小时消息限制，暂停发送")
            return False
        
        original_message = message
        
        if translate and self.translator:
            try:
                message = self.translator.translate_outgoing(message, target_lang)
            except Exception as e:
                logger.warning(f"翻译失败，使用原文: {e}")
        
        if delay is None:
            delay = MIN_REPLY_INTERVAL + random.uniform(0, 2)
        
        success = self.client.send_message(chat_id, message, delay=delay)
        
        if success:
            current_hour = datetime.now().hour
            self.db.update_message_stats(current_hour)
            
            # 保存发送的消息到数据库（带翻译）
            import time
            message_id = f"{chat_id}_sent_{time.time()}"
            self.db.save_message(
                message_id=message_id,
                chat_id=chat_id,
                contact_name=chat_id,
                message_text=message,  # 发送的翻译后的消息
                translated_text=original_message if translate and message != original_message else message,  # 原始中文消息
                is_group=False,
                is_sent=True
            )
            
            logger.info(f"消息已发送: {chat_id} -> {message[:50]}...")
        
        return success
    
    def send_batch_messages(self, chat_ids: List[str], message: str, 
                           delay_between: float = None, translate: bool = True,
                           target_lang: str = None, max_recipients: int = None) -> Dict[str, bool]:
        """批量发送消息"""
        results = {}
        
        if max_recipients is None:
            max_recipients = self.max_recipients_per_batch
        
        if delay_between is None:
            delay_between = self.batch_delay_between + random.uniform(0, 1)
        
        # 限制批量发送人数
        chat_ids = chat_ids[:max_recipients]
        
        for i, chat_id in enumerate(chat_ids):
            if not self._check_rate_limit():
                logger.warning(f"达到频率限制，停止批量发送（已发送 {i}/{len(chat_ids)}）")
                break
            
            success = self.send_message(chat_id, message, delay=delay_between, 
                                      translate=translate, target_lang=target_lang)
            results[chat_id] = success
            
            if i < len(chat_ids) - 1:
                time.sleep(delay_between)
        
        return results
    
    def schedule_message(self, chat_id: str, message: str, scheduled_time: datetime,
                        translate: bool = True, target_lang: str = None):
        """定时发送消息"""
        if translate and self.translator:
            try:
                message = self.translator.translate_outgoing(message, target_lang)
            except Exception as e:
                logger.warning(f"翻译失败: {e}")
        
        self.db.add_scheduled_message(chat_id, message, scheduled_time)
        logger.info(f"已添加定时消息: {chat_id} -> {scheduled_time}")
    
    def process_scheduled_messages(self):
        """处理待发送的定时消息（功能已禁用）"""
        pass
    
    def _check_rate_limit(self) -> bool:
        """检查消息频率限制"""
        current_hour = datetime.now().hour
        count = self.db.get_hourly_message_count(current_hour)
        return count < MAX_MESSAGES_PER_HOUR
    
    def update_settings(self, min_reply_interval: int = None, 
                       max_recipients_per_batch: int = None,
                       batch_delay_between: int = None):
        """更新设置"""
        if min_reply_interval is not None:
            self.client.set_min_reply_interval(min_reply_interval)
        
        if max_recipients_per_batch is not None:
            self.max_recipients_per_batch = max_recipients_per_batch
        
        if batch_delay_between is not None:
            self.batch_delay_between = batch_delay_between
        
        logger.info("设置已更新")
    
    def start_scheduler(self):
        """启动定时任务调度器（功能已禁用）"""
        logger.info("定时任务调度器已禁用（功能已移除）")
    
    def stop_scheduler(self):
        """停止定时任务调度器"""
        self.scheduler_running = False
        logger.info("定时任务调度器已停止")

