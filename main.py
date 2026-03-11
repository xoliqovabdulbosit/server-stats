import psutil
import sqlite3
import threading
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DB_NAME = "stats.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS stats (id INTEGER PRIMARY KEY AUTOINCREMENT, cpu REAL, ram REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

def collect_stats():
    while True:
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory().percent
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("INSERT INTO stats (cpu, ram) VALUES (?, ?)", (cpu, ram))
        time.sleep(60)  # Collect every minute

@app.get("/history")
def get_history():
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT cpu, ram, timestamp FROM stats ORDER BY timestamp DESC")
        return [dict(row) for row in cursor.fetchall()][::-1] # Return in chronological order

if __name__ == "__main__":
    init_db()
    threading.Thread(target=collect_stats, daemon=True).start()
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
