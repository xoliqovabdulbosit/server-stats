FROM python:3.11-slim

# Prevent Python from writing pyc files to disc
ENV PYTHONDONTWRITEBYTECODE=1
# Prevent Python from buffering stdout and stderr
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Pre-create directory for persistent data
RUN mkdir -p /app/data

# Install dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . /app/

EXPOSE 8001

# Production uvicorn command (no --reload)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
