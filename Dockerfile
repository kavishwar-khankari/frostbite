# ── Stage 1: Build React frontend ────────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --frozen-lockfile 2>/dev/null || npm install
COPY frontend/ .
RUN npm run build


# ── Stage 2: Python backend ───────────────────────────────────────────────────
FROM python:3.12-slim

# Install rclone
RUN apt-get update && apt-get install -y curl unzip && \
    curl -fsSL https://downloads.rclone.org/rclone-current-linux-amd64.zip -o rclone.zip && \
    unzip rclone.zip && \
    mv rclone-*-linux-amd64/rclone /usr/local/bin/ && \
    rm -rf rclone.zip rclone-*-linux-amd64 && \
    apt-get remove -y curl unzip && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Copy compiled frontend into the expected location
COPY --from=frontend-builder /build/dist ./frontend/dist

# Run Alembic migrations then start the app
CMD ["sh", "-c", "alembic upgrade head && uvicorn api.main:app --host 0.0.0.0 --port 8000"]
