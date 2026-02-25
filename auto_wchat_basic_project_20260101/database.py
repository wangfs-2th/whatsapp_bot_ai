"""
数据库模块 - 存储消息历史和配置
"""
import sqlite3
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import os
from config import DATABASE_PATH

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT UNIQUE,
                chat_id TEXT NOT NULL,
                contact_name TEXT,
                message_text TEXT NOT NULL,
                translated_text TEXT,
                is_group BOOLEAN DEFAULT 0,
                is_sent BOOLEAN DEFAULT 0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                reply_sent BOOLEAN DEFAULT 0
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scheduled_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                message_text TEXT NOT NULL,
                scheduled_time DATETIME NOT NULL,
                repeat_type TEXT,
                is_sent BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS batch_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_ids TEXT NOT NULL,
                message_text TEXT NOT NULL,
                scheduled_time DATETIME,
                is_sent BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS message_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                hour INTEGER NOT NULL,
                message_count INTEGER DEFAULT 0,
                UNIQUE(date, hour)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def message_exists(self, chat_id: str, message_text: str, timestamp: float = None, is_sent: bool = None) -> bool:
        """检查消息是否已存在于数据库中（用于避免重复处理）"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # 构建查询条件
            conditions = ['chat_id = ?', 'message_text = ?']
            params = [chat_id, message_text]
            
            if timestamp:
                # 如果提供了时间戳，检查时间戳相近的消息（±5秒内）
                from datetime import datetime, timedelta
                ts_dt = datetime.fromtimestamp(timestamp)
                ts_min = (ts_dt - timedelta(seconds=5)).isoformat()
                ts_max = (ts_dt + timedelta(seconds=5)).isoformat()
                conditions.append('timestamp BETWEEN ? AND ?')
                params.extend([ts_min, ts_max])
            
            if is_sent is not None:
                conditions.append('is_sent = ?')
                params.append(1 if is_sent else 0)
            
            query = f'SELECT COUNT(*) FROM messages WHERE {" AND ".join(conditions)}'
            cursor.execute(query, params)
            count = cursor.fetchone()[0]
            return count > 0
        except Exception as e:
            logger.error(f"检查消息是否存在时出错: {e}")
            return False
        finally:
            conn.close()
    
    def save_message(self, message_id: str, chat_id: str, contact_name: str, 
                    message_text: str, translated_text: str = None, 
                    is_group: bool = False, is_sent: bool = False):
        """保存消息到数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO messages 
                (message_id, chat_id, contact_name, message_text, translated_text, is_group, is_sent)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (message_id, chat_id, contact_name, message_text, translated_text, is_group, is_sent))
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        finally:
            conn.close()
    
    def mark_reply_sent(self, message_id: str):
        """标记消息已回复"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('UPDATE messages SET reply_sent = 1 WHERE message_id = ?', (message_id,))
        conn.commit()
        conn.close()
    
    def get_message_history(self, chat_id: str, limit: int = 50) -> List[Dict]:
        """获取聊天历史（按时间戳升序排列，最旧的消息在前）"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM messages 
            WHERE chat_id = ? 
            ORDER BY timestamp ASC 
            LIMIT ?
        ''', (chat_id, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def add_scheduled_message(self, chat_id: str, message_text: str, 
                             scheduled_time: datetime, repeat_type: str = None):
        """添加定时消息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO scheduled_messages 
            (chat_id, message_text, scheduled_time, repeat_type)
            VALUES (?, ?, ?, ?)
        ''', (chat_id, message_text, scheduled_time.isoformat(), repeat_type))
        
        conn.commit()
        conn.close()
        return cursor.lastrowid
    
    def get_pending_scheduled_messages(self) -> List[Dict]:
        """获取待发送的定时消息"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM scheduled_messages 
            WHERE is_sent = 0 AND scheduled_time <= datetime('now')
            ORDER BY scheduled_time ASC
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def mark_scheduled_sent(self, message_id: int):
        """标记定时消息已发送"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('UPDATE scheduled_messages SET is_sent = 1 WHERE id = ?', (message_id,))
        conn.commit()
        conn.close()
    
    def update_message_stats(self, hour: int):
        """更新消息统计"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now().date().isoformat()
        
        cursor.execute('''
            INSERT INTO message_stats (date, hour, message_count)
            VALUES (?, ?, 1)
            ON CONFLICT(date, hour) DO UPDATE SET message_count = message_count + 1
        ''', (today, hour))
        
        conn.commit()
        conn.close()
    
    def get_hourly_message_count(self, hour: int) -> int:
        """获取指定小时的消息数量"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now().date().isoformat()
        cursor.execute('''
            SELECT message_count FROM message_stats 
            WHERE date = ? AND hour = ?
        ''', (today, hour))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else 0





