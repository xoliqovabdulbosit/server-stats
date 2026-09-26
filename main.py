from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
import psutil
import sqlite3
import asyncio
from datetime import datetime, timedelta, timezone
from fastapi.responses import FileResponse

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    task = asyncio.create_task(metrics_logger())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)

import os
import logging
from pathlib import Path

logger = logging.getLogger("uvicorn.error")

DB_PATH = os.getenv("DB_PATH", "metrics.db")
INDEX_PATH = Path(__file__).resolve().parent / "index.html"

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    db_file = Path(DB_PATH)
    if db_file.parent and not db_file.parent.exists():
        db_file.parent.mkdir(parents=True, exist_ok=True)

    conn = get_db()
    with conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS system_metrics
                        (timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, cpu REAL, ram REAL, disk REAL)''')
        conn.execute('''CREATE INDEX IF NOT EXISTS idx_system_metrics_timestamp 
                        ON system_metrics(timestamp)''')
    conn.close()

def clean_old_metrics(days: int = 30):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_str = cutoff.strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM system_metrics WHERE timestamp < ?", (cutoff_str,))
    conn.close()

def log_metrics():
    # Capture metrics
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent

    conn = get_db()
    with conn:
        conn.execute("INSERT INTO system_metrics (cpu, ram, disk) VALUES (?, ?, ?)", (cpu, ram, disk))
    conn.close()

async def metrics_logger():
    # Run initial cleanup on startup
    try:
        clean_old_metrics()
    except Exception as e:
        logger.error(f"Error during startup metrics cleanup: {e}")

    cleanup_counter = 0

    while True:
        try:
            log_metrics()
            cleanup_counter += 1
            # Run cleanup approximately once an hour (every 60 iterations * 60s)
            if cleanup_counter >= 60:
                clean_old_metrics()
                cleanup_counter = 0
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error capturing system metrics: {e}")

        await asyncio.sleep(60)

@app.get("/")
async def read_index():
    if not INDEX_PATH.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(INDEX_PATH)

@app.get("/data/{period}")
def get_data(period: str):
    # Aligning Python's datetime calculations with SQLite's UTC timestamps
    now_utc = datetime.now(timezone.utc)

    query = ""
    params = []

    if period == "today":
        # Start of today (00:00:00 UTC)
        start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        start_str = start.strftime('%Y-%m-%d %H:%M:%S')

        # Grouping by 1 minute: strftime('%Y-%m-%d %H:%M:00', timestamp)
        query = """
            SELECT strftime('%Y-%m-%d %H:%M:00', timestamp) AS interval_time, MAX(cpu), MAX(ram), MAX(disk)
            FROM system_metrics
            WHERE timestamp >= ?
            GROUP BY interval_time
            ORDER BY interval_time ASC
        """
        params = [start_str]

    elif period == "yesterday":
        # Start and end of yesterday (00:00:00 to 23:59:59 UTC)
        start = (now_utc - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

        start_str = start.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end.strftime('%Y-%m-%d %H:%M:%S')

        # Grouping by 1 minute for yesterday's range
        query = """
            SELECT strftime('%Y-%m-%d %H:%M:00', timestamp) AS interval_time, MAX(cpu), MAX(ram), MAX(disk)
            FROM system_metrics
            WHERE timestamp >= ? AND timestamp < ?
            GROUP BY interval_time
            ORDER BY interval_time ASC
        """
        params = [start_str, end_str]

    elif period == "week":
        # Last 7 days, grouping by 5 minutes (300 seconds)
        start = now_utc - timedelta(days=7)
        start_str = start.strftime('%Y-%m-%d %H:%M:%S')

        query = """
            SELECT datetime(strftime('%s', timestamp) / 300 * 300, 'unixepoch') AS interval_time, MAX(cpu), MAX(ram), MAX(disk)
            FROM system_metrics
            WHERE timestamp >= ?
            GROUP BY interval_time
            ORDER BY interval_time ASC
        """
        params = [start_str]

    elif period == "month":
        # Last 30 days, grouping by 30 minutes (1800 seconds)
        start = now_utc - timedelta(days=30)
        start_str = start.strftime('%Y-%m-%d %H:%M:%S')

        query = """
            SELECT datetime(strftime('%s', timestamp) / 1800 * 1800, 'unixepoch') AS interval_time, MAX(cpu), MAX(ram), MAX(disk)
            FROM system_metrics
            WHERE timestamp >= ?
            GROUP BY interval_time
            ORDER BY interval_time ASC
        """
        params = [start_str]

    else:
        raise HTTPException(status_code=404, detail="Period not found")

    conn = get_db()
    cursor = conn.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return {
        "labels": [r[0] for r in rows],
        "cpu": [r[1] for r in rows],
        "ram": [r[2] for r in rows],
        "disk": [r[3] for r in rows]
    }
