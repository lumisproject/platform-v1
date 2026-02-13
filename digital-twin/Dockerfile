FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# --- STEP 1: Install the "Heavy" libraries manually ---
# This layer will be cached and NEVER re-downloaded unless you change this specific line
RUN pip install --no-cache-dir sentence-transformers

# --- STEP 2: Install the rest of your requirements ---
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- STEP 3: Copy code ---
COPY src/ ./src/
COPY main.py .

RUN mkdir -p /app/memory
VOLUME ["/app/memory"]

CMD ["python", "main.py"]