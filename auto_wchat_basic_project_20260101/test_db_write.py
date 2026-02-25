from database import Database
from datetime import datetime
import time

"""
简单测试：往 whatsapp_bot.db 的 messages 表写入一条测试记录。
运行方式：在项目根目录执行
    python test_db_write.py
"""

def main():
    db = Database()
    ts = datetime.now().isoformat(sep=' ', timespec='seconds')
    message_id = f"test_{time.time()}"

    db.save_message(
        message_id=message_id,
        chat_id="TestContact",
        contact_name="测试联系人",
        message_text=f"这是一条测试消息，时间 {ts}",
        translated_text=None,
        is_group=False,
        is_sent=True,
    )

    print("已写入测试消息，message_id =", message_id)

    # 读取该 chat 的最近几条消息验证
    history = db.get_message_history("TestContact", limit=5)
    print("最近消息记录:")
    for row in history:
        print(row)


if __name__ == "__main__":
    main()






