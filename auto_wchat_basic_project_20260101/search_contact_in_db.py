import sqlite3
import os

DB_PATH = 'whatsapp_bot.db'

def search_contact(name: str):
    path = os.path.abspath(DB_PATH)
    print('DB path:', path)
    if not os.path.exists(DB_PATH):
        print('Database file does not exist')
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    try:
        # 在 chat_id 和 contact_name 中模糊搜索
        like = f'%{name}%'
        cur.execute(
            '''
            SELECT DISTINCT chat_id, contact_name, is_group, is_sent, timestamp
            FROM messages
            WHERE chat_id LIKE ? OR contact_name LIKE ?
            ORDER BY timestamp DESC
            ''',
            (like, like),
        )
        rows = cur.fetchall()
        if not rows:
            print(f'No messages found for contact like "{name}".')
        else:
            print(f'Found {len(rows)} conversation(s) for "{name}":')
            for r in rows:
                print(dict(r))
    finally:
        conn.close()


if __name__ == '__main__':
    search_contact('Jun Cu')






