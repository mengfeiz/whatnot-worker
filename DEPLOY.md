"""
Deploy to Railway:

1. Create a new Railway service from this directory
2. Set environment variables:
   - HEADLESS=true
   - SLOW_MO_MS=100
3. Railway will auto-detect Dockerfile and build
4. The worker exposes port 8080

Login flow for Google Auth:
- Option A: Export cookies from your browser and POST to /login/restore
- Option B: Run once with HEADLESS=false via VNC, complete Google OAuth manually

Usage from OpenClaw agent:
  curl -X POST https://<your-worker>.up.railway.app/exec \
    -H "Content-Type: application/json" \
    -d '{"operation": "check_login", "params": {}}'

  curl -X POST https://<your-worker>.up.railway.app/exec \
    -H "Content-Type: application/json" \
    -d '{"operation": "get_listings", "params": {}}'

  curl -X POST https://<your-worker>.up.railway.app/exec \
    -H "Content-Type: application/json" \
    -d '{"operation": "screenshot", "params": {"label": "listings_check"}}'
"""
