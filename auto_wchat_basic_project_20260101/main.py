"""
WhatsApp自动聊天程序主入口
"""
import logging
import signal
import sys
import time
from threading import Thread
from whatsapp_client import WhatsAppClient
from auto_reply import AutoReply, ScheduledReply
from message_sender import MessageSender
from database import Database
from file_reader import ContentManager
from web_server import WebServer
from config import (
    AUTO_REPLY_ENABLED, SCHEDULED_MESSAGES_ENABLED
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('whatsapp_bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class WhatsAppBot:
    def __init__(self):
        self.client = WhatsAppClient()
        self.db = Database()
        self.content_manager = ContentManager()
        # 记录系统启动时间（用于判断只回复启动后的新消息）
        self.start_time = time.time()
        self.auto_reply = AutoReply(self.client, self.db, self.content_manager, start_time=self.start_time)
        self.scheduled_reply = ScheduledReply(self.client, self.db)
        self.message_sender = MessageSender(self.client, self.db)
        self.web_server = None
        self.running = False
    
    def start(self):
        """启动机器人"""
        if self.running:
            logger.warning("机器人已在运行")
            return
        
        self.running = True
        # 更新启动时间（如果重新启动）
        self.start_time = time.time()
        self.auto_reply.start_time = self.start_time
        
        from datetime import datetime
        start_time_str = datetime.fromtimestamp(self.start_time).strftime('%Y-%m-%d %H:%M:%S')
        logger.info("=" * 60)
        logger.info("WhatsApp自动聊天机器人启动...")
        logger.info(f"系统启动时间: {start_time_str}")
        logger.info(f"自动回复功能: {'✅ 已启用' if AUTO_REPLY_ENABLED else '❌ 未启用'}")
        logger.info(f"登录状态: {'✅ 已登录' if self.client.is_logged_in else '❌ 未登录'}")
        logger.info("=" * 60)
        logger.info("📌 重要提示: 只回复系统启动后收到的新消息，启动前的消息不会处理")
        
        if AUTO_REPLY_ENABLED:
            logger.info("正在启动消息监听线程...")
            listener_thread = Thread(
                target=self._message_listener,
                daemon=True
            )
            listener_thread.start()
            logger.info("✅ 消息监听线程已创建并启动")
        else:
            logger.warning("⚠️  自动回复功能未启用，消息监听不会启动")
            logger.warning("如需启用，请在配置文件中设置 AUTO_REPLY_ENABLED=True")
        
        logger.info("机器人运行中... (按 Ctrl+C 退出)")
    
    def _message_listener(self):
        """消息监听线程"""
        logger.info("📡 消息监听线程已启动")
        logger.info(f"登录状态: {self.client.is_logged_in}")
        
        def handle_message(chat_id, contact_name, message, is_group, is_sent=False, message_id=None, message_timestamp=None, msg_index=None):
            try:
                # 如果回调中没有提供message_id，则生成一个
                # 优先使用whatsapp_client.py中生成的message_id格式，确保一致性
                if not message_id:
                    import random
                    # 使用与whatsapp_client.py相同的格式：联系人 + 消息文本 + 时间戳 + 索引
                    if message_timestamp is not None and msg_index is not None:
                        message_id = f"{contact_name}_{message}_{message_timestamp}_{msg_index}"
                    else:
                        # 降级方案：使用时间戳和随机数
                        message_id = f"{contact_name}_{hash(message)}_{time.time()}_{random.randint(1000, 9999)}"
                logger.info(f"📨 收到消息回调: {contact_name}, 消息: {message[:50]}..., 方向: {'发送' if is_sent else '接收'}, message_id: {message_id}")
                self.auto_reply.handle_message(
                    chat_id=chat_id,
                    contact_name=contact_name,
                    message=message,
                    is_group=is_group,
                    message_id=message_id,
                    is_sent=is_sent,
                    message_timestamp=message_timestamp
                )
            except Exception as e:
                logger.error(f"处理消息时出错: {e}", exc_info=True)
        
        try:
            logger.info("正在调用 listen_messages() 开始监听循环...")
            self.client.listen_messages(handle_message)
            logger.warning("listen_messages() 函数已返回，监听循环可能已退出")
        except Exception as e:
            logger.error(f"消息监听出错: {e}", exc_info=True)
            if self.running:
                logger.info("5秒后重新启动监听线程...")
                time.sleep(5)
                self._message_listener()
            else:
                logger.info("机器人已停止，不再重启监听线程")
    
    def stop(self):
        """停止机器人"""
        if not self.running:
            return
        
        logger.info("正在停止机器人...")
        self.running = False
        
        self.message_sender.stop_scheduler()
        self.client.close()
        
        logger.info("机器人已停止")
    
    def send_message(self, chat_id: str, message: str, translate: bool = True, 
                    target_lang: str = None) -> bool:
        """发送消息"""
        return self.message_sender.send_message(
            chat_id, message, translate=translate, target_lang=target_lang
        )
    
    def send_batch(self, chat_ids: list, message: str, translate: bool = True,
                  target_lang: str = None) -> dict:
        """批量发送消息"""
        return self.message_sender.send_batch_messages(
            chat_ids, message, translate=translate, target_lang=target_lang
        )
    
    def schedule_message(self, chat_id: str, message: str, scheduled_time,
                        translate: bool = True, target_lang: str = None):
        """定时发送消息"""
        self.message_sender.schedule_message(
            chat_id, message, scheduled_time, translate=translate, target_lang=target_lang
        )


def main():
    """主函数"""
    bot = WhatsAppBot()
    
    bot.web_server = WebServer(bot_instance=bot)
    
    def signal_handler(sig, frame):
        logger.info("收到退出信号...")
        bot.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        print("\n=== WhatsApp自动聊天机器人 ===")
        print("正在启动Web界面...")
        print("浏览器将自动打开，请在Web界面中登录WhatsApp")
        
        server_thread = Thread(
            target=bot.web_server.run,
            args=('127.0.0.1', 5001, False, True),
            daemon=True
        )
        server_thread.start()
        
        # 等待一下，让服务器有时间启动并报告实际端口
        import time
        time.sleep(0.5)
        
        logger.info("Web服务器正在启动...")
        logger.info("请在Web界面中操作...")
        
        while True:
            time.sleep(1)
    
    except KeyboardInterrupt:
        logger.info("用户中断程序")
    except Exception as e:
        logger.error(f"程序出错: {e}", exc_info=True)
    finally:
        bot.stop()


if __name__ == "__main__":
    main()





