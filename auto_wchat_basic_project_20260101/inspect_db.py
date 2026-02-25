import sqlite3
import os

DB_PATH = 'whatsapp_bot.db'

print('DB path:', os.path.abspath(DB_PATH))
print('Exists:', os.path.exists(DB_PATH))
if not os.path.exists(DB_PATH):
    raise SystemExit('Database file does not exist')

print('Size:', os.path.getsize(DB_PATH), 'bytes')

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

try:
    cur.execute('SELECT COUNT(*) AS cnt FROM messages')
    row = cur.fetchone()
    print('messages count:', row['cnt'] if row else 0)

    cur.execute('SELECT chat_id, contact_name, message_text, is_group, is_sent, timestamp FROM messages ORDER BY timestamp DESC LIMIT 10')
    rows = cur.fetchall()
    print('Last 10 messages:')
    for r in rows:
        print(dict(r))
finally:
    conn.close()






