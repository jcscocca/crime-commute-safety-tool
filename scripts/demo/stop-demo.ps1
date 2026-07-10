# Tear down the demo instance AND the quick tunnel (the cloudflared process is the
# tunnel; its URL dies with it).
$ErrorActionPreference = "Stop"
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
docker compose -p waypoint-demo -f docker-compose.yml -f docker-compose.demo.yml --env-file .env.demo down
Write-Host "Demo instance stopped. DB volume kept (docker volume rm waypoint-demo_* to wipe)."
