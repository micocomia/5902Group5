FROM python:3.13-slim

WORKDIR /app

# Install system dependencies needed to build Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and filter out macOS-only version pins before installing
COPY requirements.txt .
RUN grep -ivE '^watchdog==' requirements.txt > requirements-docker.txt \
    && pip install --no-cache-dir -r requirements-docker.txt \
    && rm requirements-docker.txt

# Copy application code
COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "main.py", "--server.port=8501", "--server.address=0.0.0.0"]
