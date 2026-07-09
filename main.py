from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
import psutil
import sqlite3
import asyncio
from datetime import datetime, timedelta
from fastapi.responses import FileResponse

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    task = asyncio.create_task(metrics_logger())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)

def init_db():
    conn = sqlite3.connect('metrics.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS system_metrics
                    (timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, cpu REAL, ram REAL, disk REAL)''')
    conn.commit()
    conn.close()

def log_metrics():
    # Capture metrics
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent

    conn = sqlite3.connect('metrics.db')
    conn.execute("INSERT INTO system_metrics (cpu, ram, disk) VALUES (?, ?, ?)", (cpu, ram, disk))
    conn.commit()
    conn.close()

async def metrics_logger():
    while True:
        log_metrics()
        await asyncio.sleep(60)

@app.get("/")
async def read_index():
    return FileResponse('index.html')

@app.get("/data/{period}")
def get_data(period: str):
    now = datetime.now()
    if period == "today": start = now.replace(hour=0, minute=0, second=0)
    elif period == "yesterday": start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0)
    elif period == "week": start = now - timedelta(days=7)
    elif period == "month": start = now - timedelta(days=30)
    else: raise HTTPException(status_code=404, detail="Item not found")

    conn = sqlite3.connect('metrics.db')
    cursor = conn.execute("SELECT timestamp, cpu, ram, disk FROM system_metrics WHERE timestamp >= ?", (start,))
    rows = cursor.fetchall()
    conn.close()
    return {
        "labels": [r[0] for r in rows],
        "cpu": [r[1] for r in rows],
        "ram": [r[2] for r in rows],
        "disk": [r[3] for r in rows]
    }
