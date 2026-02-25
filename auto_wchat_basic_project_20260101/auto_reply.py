"""
自动回复模块 - 实现关键词触发、AI回复、定时回复等功能
"""
import time
import logging
import random
import importlib
from typing import Optional, Dict, List
from datetime import datetime, timedelta
from config import (
    AUTO_REPLY_ENABLED, REPLY_DELAY, KEYWORD_REPLIES, DEFAULT_REPLY,
    LISTEN_CONTACTS, SPECIFIC_CONTACTS
)
from ai_reply import AIReply, LocalContentReply
from translator import Translator
from database import Database

logger = logging.getLogger(__name__)


class AutoReply:
    def __init__(self, whatsapp_client, database: Database, content_manager=None, start_time=None):
        self.client = whatsapp_client
        self.db = database
        self.ai_reply = AIReply()
        self.local_content = LocalContentReply()
        self.translator = Translator()
        self.content_manager = content_manager
        self.enabled = AUTO_REPLY_ENABLED
        self.reply_stats = {}
        # 记录系统启动时间（用于判断只回复启动后的新消息）
        self.start_time = start_time if start_time is not None else time.time()
    
    def _get_config(self):
        """动态获取最新配置"""
        import config
        importlib.reload(config)
        from config import (
            AUTO_REPLY_ENABLED, LISTEN_CONTACTS, 
            SPECIFIC_CONTACTS,
            REPLY_TO_ALL_CONTACTS
        )
        return {
            'auto_reply_enabled': AUTO_REPLY_ENABLED,
            'listen_contacts': LISTEN_CONTACTS,
            'reply_to_all_contacts': REPLY_TO_ALL_CONTACTS,
            'specific_contacts': [c.strip() for c in SPECIFIC_CONTACTS if c.strip()]
        }
    
    def should_reply(self, chat_id: str, contact_name: str, is_group: bool) -> bool:
        """判断是否应该回复"""
        # 动态获取最新配置
        config = self._get_config()
        
        # 更新实例的enabled状态
        self.enabled = config['auto_reply_enabled']
        
        if not config['auto_reply_enabled']:
            logger.debug(f"自动回复功能未启用，跳过回复: {contact_name}")
            return False
        
        # 不处理群组消息
        if is_group:
            return False
        
        if not config['listen_contacts']:
            return False
        
        # 清理联系人名称（去除首尾空格）
        contact_name_clean = contact_name.strip() if contact_name else ""
        
        # 联系人判断
        if config['reply_to_all_contacts']:
            # 如果设置为回复所有人，直接返回True
            logger.info(f"设置为回复所有联系人，允许自动回复: {contact_name_clean}")
        else:
            # 如果设置为只回复指定联系人，检查是否在列表中
            if not config['specific_contacts']:
                logger.info(f"未设置特定联系人列表且未启用回复所有人，跳过回复: {contact_name_clean}")
                return False
            
            contact_matched = False
            for specific_contact in config['specific_contacts']:
                if specific_contact.strip().lower() == contact_name_clean.lower():
                    contact_matched = True
                    logger.info(f"联系人 {contact_name_clean} 匹配到特定联系人列表中的: {specific_contact}")
                    break
            
            if not contact_matched:
                logger.info(f"联系人 {contact_name_clean} 不在特定联系人列表中: {config['specific_contacts']}")
                return False
        
        logger.info(f"允许自动回复: {contact_name_clean}")
        return True
    
    def generate_reply(self, message: str, chat_id: str, contact_name: str) -> Optional[str]:
        """生成回复消息"""
        logger.info(f"   正在尝试生成回复...")
        logger.info(f"   联系人: {contact_name} (聊天ID: {chat_id})")
        
        # 1. 尝试关键词回复
        logger.info(f"   1️⃣ 检查关键词匹配...")
        reply = self._check_keyword_reply(message)
        if reply:
            logger.info(f"   ✓ 关键词匹配成功，使用关键词回复")
            logger.info(f"   回复内容: {reply}")
            return reply
        logger.info(f"   ✗ 未匹配到关键词")
        
        # 2. 尝试本地内容回复
        logger.info(f"   2️⃣ 检查本地内容匹配...")
        reply = self.local_content.get_reply(message)
        if reply:
            logger.info(f"   ✓ 本地内容匹配成功，使用本地内容回复")
            logger.info(f"   回复内容: {reply}")
            return reply
        logger.info(f"   ✗ 未匹配到本地内容")
        
        # 3. 尝试AI回复
        logger.info(f"   3️⃣ 尝试AI生成回复...")
        if not self.ai_reply.is_available():
            logger.warning(f"   ✗ AI功能不可用，使用默认回复")
            logger.info(f"   默认回复: {DEFAULT_REPLY}")
            return DEFAULT_REPLY
        
        logger.info(f"   ✓ AI功能可用，开始调用AI生成回复...")
        
        # 获取聊天历史（只使用联系人的消息，不包括自己发送的消息）
        all_history = self.db.get_message_history(chat_id, limit=20)
        # 过滤出只有联系人的消息（is_sent=False）
        chat_history = [msg for msg in all_history if not msg.get('is_sent', False)]
        logger.info(f"   聊天历史: 总共 {len(all_history)} 条，联系人消息 {len(chat_history)} 条（已过滤掉自己发送的消息）")
        
        # 获取文件内容
        file_content = None
        if self.content_manager:
            file_content = self.content_manager.get_all_content()
            if file_content:
                logger.info(f"   知识库内容: {len(file_content)} 字符")
            else:
                logger.info(f"   知识库内容: 无")
        
        # 调用AI生成回复（只基于联系人的消息）
        logger.info(f"   📡 调用AI API生成回复（基于联系人的消息）...")
        reply, error_msg = self.ai_reply.generate_reply(
            message, 
            chat_history, 
            file_content=file_content
        )
        
        if reply:
            logger.info(f"   ✅ AI生成回复成功")
            logger.info(f"   回复内容: {reply}")
            return reply
        elif error_msg:
            logger.warning(f"   ⚠️  AI生成回复失败: {error_msg}")
            logger.info(f"   使用默认回复: {DEFAULT_REPLY}")
            return DEFAULT_REPLY
        
        logger.warning(f"   ⚠️  AI未返回回复，使用默认回复")
        return DEFAULT_REPLY
    
    def _check_keyword_reply(self, message: str) -> Optional[str]:
        """检查关键词回复"""
        message_lower = message.lower()
        
        for keyword, reply in KEYWORD_REPLIES.items():
            if keyword.lower() in message_lower:
                return reply
        
        return None
    
    def handle_message(self, chat_id: str, contact_name: str, message: str, 
                      is_group: bool, message_id: str = None, is_sent: bool = False, 
                      message_timestamp: float = None):
        """处理收到的消息并自动回复"""
        # 记录收到的消息
        logger.info(f"═══════════════════════════════════════════════════════════")
        logger.info(f"📨 收到新消息")
        logger.info(f"   联系人: {contact_name}")
        logger.info(f"   类型: 联系人")
        logger.info(f"   方向: {'发送' if is_sent else '接收'}")
        logger.info(f"   消息ID: {message_id or 'N/A'}")
        logger.info(f"   聊天ID: {chat_id}")
        logger.info(f"   消息内容: {message}")
        logger.info(f"   消息长度: {len(message)} 字符")
        
        # 如果是自己发送的消息，不需要自动回复，也不保存到数据库（避免重复显示）
        if is_sent:
            logger.info(f"⏸️  跳过自动回复和保存: 这是自己发送的消息")
            logger.info(f"═══════════════════════════════════════════════════════════")
            return
        
        # 🔒 检查消息时间戳：只处理系统启动后收到的新消息
        # 允许5秒的容差，避免第一条消息因时间戳精度问题被误判
        time_tolerance = 5.0  # 5秒容差
        
        if message_timestamp is not None:
            from datetime import datetime
            message_time_str = datetime.fromtimestamp(message_timestamp).strftime('%Y-%m-%d %H:%M:%S')
            start_time_str = datetime.fromtimestamp(self.start_time).strftime('%Y-%m-%d %H:%M:%S')
            time_diff = message_timestamp - self.start_time
            
            # 如果消息时间戳早于启动时间超过容差，才跳过
            if message_timestamp < (self.start_time - time_tolerance):
                logger.info(f"⏸️  跳过自动回复: 消息时间 ({message_time_str}) 早于系统启动时间 ({start_time_str})")
                logger.info(f"   时间差: {time_diff:.2f} 秒，超过容差 ({time_tolerance} 秒)")
                logger.info(f"   只处理系统启动后收到的新消息，启动前的消息不会处理")
                logger.info(f"═══════════════════════════════════════════════════════════")
                return
            else:
                if time_diff < 0:
                    logger.info(f"✅ 消息时间 ({message_time_str}) 略早于系统启动时间 ({start_time_str})，但在容差范围内 ({time_diff:.2f} 秒)，继续处理")
                else:
                    logger.info(f"✅ 消息时间 ({message_time_str}) 晚于或等于系统启动时间 ({start_time_str})，时间差: {time_diff:.2f} 秒，继续处理")
        else:
            # 如果没有时间戳，记录警告但继续处理（降级方案）
            # 对于没有时间戳的消息，假设是启动后收到的新消息
            logger.warning(f"⚠️  消息没有时间戳，假设是启动后收到的新消息，继续处理")
        
        # 🔒 防重复检查1: 检查数据库中是否已存在相同的消息（避免重复处理）
        # 对于启动后收到的第一条消息，放宽检查条件（允许处理）
        if message_id:
            try:
                # 检查消息是否已存在且已回复
                if self.db.message_exists(chat_id, message, is_sent=False):
                    logger.info(f"🔍 检查消息是否已处理...")
                    # 获取最近的消息记录，检查是否已回复
                    recent_messages = self.db.get_message_history(chat_id, limit=10)
                    found_replied = False
                    for msg in recent_messages:
                        if (msg.get('message_text') == message and 
                            msg.get('is_sent') == False and 
                            msg.get('reply_sent') == 1):
                            # 检查这条已回复的消息的时间戳
                            # 如果是在启动前回复的，允许重新处理（可能是启动后的新消息）
                            msg_timestamp = msg.get('timestamp')
                            if msg_timestamp:
                                try:
                                    from datetime import datetime
                                    if isinstance(msg_timestamp, str):
                                        # 尝试解析字符串格式的时间戳
                                        try:
                                            msg_dt = datetime.fromisoformat(msg_timestamp.replace('Z', '+00:00'))
                                            msg_ts = msg_dt.timestamp()
                                        except:
                                            # 如果解析失败，尝试其他格式
                                            msg_dt = datetime.strptime(msg_timestamp, '%Y-%m-%d %H:%M:%S')
                                            msg_ts = msg_dt.timestamp()
                                    else:
                                        msg_ts = msg_timestamp
                                    
                                    # 如果已回复的消息是在启动前保存的，允许处理新消息
                                    if msg_ts < self.start_time:
                                        logger.info(f"   已回复的消息是在启动前保存的（时间戳: {msg_ts} < 启动时间: {self.start_time}），允许处理启动后的新消息")
                                        found_replied = False
                                        break
                                except Exception as e:
                                    logger.debug(f"   解析消息时间戳时出错: {e}，继续检查")
                            
                            found_replied = True
                            logger.warning(f"⚠️  检测到重复消息且已回复过，跳过处理")
                            logger.info(f"   消息ID: {msg.get('message_id')}")
                            logger.info(f"   已回复标记: {msg.get('reply_sent')}")
                            logger.info(f"═══════════════════════════════════════════════════════════")
                            break
                    
                    if found_replied:
                        return
            except Exception as e:
                logger.warning(f"⚠️  检查消息是否存在时出错: {e}，继续处理")
        
        # 翻译消息（无论是否回复，都先翻译以便保存）
        translated_message = message
        if self.translator:
            try:
                logger.info(f"🌐 开始翻译消息...")
                translated_message = self.translator.translate_to_chinese(message)
                if translated_message != message:
                    logger.info(f"   原文: {message[:100]}...")
                    logger.info(f"   译文: {translated_message[:100]}...")
                else:
                    logger.info(f"   消息已经是中文，无需翻译")
            except Exception as e:
                logger.warning(f"⚠️  翻译失败: {e}，使用原文")
        
        # 保存消息到数据库（只保存联系人的消息，以便在聊天窗口中显示）
        if message_id:
            try:
                logger.info(f"💾 保存消息到数据库...")
                self.db.save_message(
                    message_id=message_id,
                    chat_id=chat_id,
                    contact_name=contact_name,
                    message_text=message,
                    translated_text=translated_message,
                    is_group=is_group,
                    is_sent=False  # 联系人的消息，is_sent=False
                )
                logger.info(f"   ✓ 消息已保存到数据库 (is_sent=False)")
            except Exception as e:
                logger.error(f"   ✗ 保存消息失败: {e}")
        
        # 检查是否应该回复
        if not self.should_reply(chat_id, contact_name, is_group):
            logger.info(f"⏸️  跳过自动回复: {contact_name} - 不符合自动回复条件")
            logger.info(f"   消息已保存，可在聊天窗口中查看")
            logger.info(f"═══════════════════════════════════════════════════════════")
            return
        
        # 🔒 防重复检查2: 再次检查是否已回复过（防止并发情况）
        # 对于启动后收到的消息，只检查启动后保存的消息
        if message_id:
            try:
                recent_messages = self.db.get_message_history(chat_id, limit=5)
                for msg in recent_messages:
                    if (msg.get('message_text') == message and 
                        msg.get('is_sent') == False and 
                        msg.get('reply_sent') == 1):
                        # 检查这条已回复的消息是否是在启动后保存的
                        msg_timestamp = msg.get('timestamp')
                        if msg_timestamp:
                            try:
                                from datetime import datetime
                                if isinstance(msg_timestamp, str):
                                    msg_dt = datetime.fromisoformat(msg_timestamp.replace('Z', '+00:00'))
                                    msg_ts = msg_dt.timestamp()
                                else:
                                    msg_ts = msg_timestamp
                                
                                # 如果已回复的消息是在启动前保存的，允许处理新消息
                                if msg_ts < self.start_time:
                                    logger.debug(f"   已回复的消息是在启动前保存的，允许处理启动后的新消息")
                                    continue
                            except:
                                pass
                        
                        logger.warning(f"⚠️  检测到消息已回复过（并发检查），跳过重复回复")
                        logger.info(f"═══════════════════════════════════════════════════════════")
                        return
            except Exception as e:
                logger.debug(f"并发检查时出错: {e}，继续处理")
        
        logger.info(f"✅ 允许自动回复，开始处理...")
        
        # 生成回复
        logger.info(f"🤖 开始生成AI回复...")
        logger.info(f"   联系人: {contact_name}")
        logger.info(f"   聊天ID: {chat_id}")
        logger.info(f"   类型: 联系人")
        logger.info(f"   使用消息: {translated_message or message}")
        reply = self.generate_reply(translated_message or message, chat_id, contact_name)
        
        if not reply:
            logger.warning(f"⚠️  未能生成回复，终止处理")
            logger.info(f"═══════════════════════════════════════════════════════════")
            return
        
        logger.info(f"✅ AI回复生成成功")
        logger.info(f"   回复内容: {reply}")
        logger.info(f"   回复长度: {len(reply)} 字符")
        
        # 计算延迟时间
        delay = REPLY_DELAY + random.uniform(0, 2)
        logger.info(f"⏱️  等待 {delay:.2f} 秒后发送回复（延迟设置: {REPLY_DELAY}秒）...")
        time.sleep(delay)
        
        # 获取自动回复语言设置
        import importlib
        import config
        importlib.reload(config)
        from config import AUTO_REPLY_LANGUAGE
        
        # 发送回复（根据设置的语言进行翻译）
        logger.info(f"📤 开始发送回复...")
        logger.info(f"   目标: {contact_name} ({chat_id})")
        logger.info(f"   回复语言: {AUTO_REPLY_LANGUAGE}")
        logger.info(f"   原始回复内容: {reply[:100]}...")
        
        # 如果设置了语言且不是中文，需要翻译
        translated_reply = reply
        if AUTO_REPLY_LANGUAGE and AUTO_REPLY_LANGUAGE != 'zh' and self.translator:
            try:
                translated_reply = self.translator.translate_outgoing(reply, AUTO_REPLY_LANGUAGE)
                logger.info(f"   翻译后回复内容: {translated_reply[:100]}...")
            except Exception as e:
                logger.warning(f"   翻译失败，使用原始回复: {e}")
                translated_reply = reply
        
        success = self.client.send_message(chat_id, translated_reply, delay=delay)
        
        if success:
            logger.info(f"✅ 回复发送成功")
            
            # 保存 AI 自动回复的消息到数据库，标记为已发送（显示在右边）
            reply_message_id = f"{chat_id}_ai_reply_{time.time()}"
            try:
                self.db.save_message(
                    message_id=reply_message_id,
                    chat_id=chat_id,
                    contact_name=contact_name,
                    message_text=translated_reply,  # 发送的翻译后的消息
                    translated_text=reply,  # AI 回复的原始中文消息
                    is_group=is_group,
                    is_sent=True  # 标记为已发送，显示在右边
                )
                logger.info(f"   ✓ AI回复消息已保存到数据库（is_sent=True，将显示在右边）")
            except Exception as e:
                logger.warning(f"   ⚠️  保存AI回复消息失败: {e}")
            
            # 🔒 标记原消息为已回复（防止重复回复）
            if message_id:
                try:
                    self.db.mark_reply_sent(message_id)
                    logger.info(f"   ✓ 已标记消息为已回复 (message_id: {message_id})")
                except Exception as e:
                    logger.warning(f"   ⚠️  标记消息失败: {e}")
            else:
                # 如果没有message_id，尝试通过消息内容查找并标记
                try:
                    recent_messages = self.db.get_message_history(chat_id, limit=10)
                    for msg in recent_messages:
                        if (msg.get('message_text') == message and 
                            msg.get('is_sent') == False and 
                            msg.get('reply_sent') == 0):
                            self.db.mark_reply_sent(msg.get('message_id'))
                            logger.info(f"   ✓ 已通过消息内容标记为已回复 (message_id: {msg.get('message_id')})")
                            break
                except Exception as e:
                    logger.debug(f"通过消息内容标记时出错: {e}")
            
            self.reply_stats[chat_id] = self.reply_stats.get(chat_id, 0) + 1
            logger.info(f"   统计: 该联系人已回复 {self.reply_stats[chat_id]} 次")
            logger.info(f"═══════════════════════════════════════════════════════════")
        else:
            logger.error(f"❌ 回复发送失败: {contact_name}")
            logger.error(f"   可能原因: WhatsApp连接问题、联系人不存在、消息格式错误等")
            logger.info(f"═══════════════════════════════════════════════════════════")
    
    def set_ai_personality(self, personality: str):
        """设置AI人物特点"""
        self.ai_reply.set_personality(personality)
        logger.info(f"AI人物特点已更新: {personality}")


class ScheduledReply:
    """定时回复模块"""
    
    def __init__(self, whatsapp_client, database: Database):
        self.client = whatsapp_client
        self.db = database
        self.translator = Translator()
    
    def process_scheduled_replies(self):
        """处理待发送的定时回复"""
        pending_messages = self.db.get_pending_scheduled_messages()
        
        for msg in pending_messages:
            try:
                success = self.client.send_message(
                    msg['chat_id'],
                    msg['message_text']
                )
                
                if success:
                    self.db.mark_scheduled_sent(msg['id'])
                    logger.info(f"定时回复已发送: {msg['chat_id']}")
            
            except Exception as e:
                logger.error(f"发送定时回复失败: {e}")



