FROM mcr.microsoft.com/playwright/python:v1.52.0-noble

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stealth plugin for anti-detection
RUN npx -y playwright-extra@latest 2>/dev/null || true

COPY . .

# Persistent storage for browser state (cookies, localStorage)
RUN mkdir -p /data/browser-state
ENV BROWSER_STATE_DIR=/data/browser-state

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

CMD ["python", "server.py"]
