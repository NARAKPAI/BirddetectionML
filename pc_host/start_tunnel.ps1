param (
    [int]$HttpPort = 8000
)

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Error "cloudflared is not installed. Download it from https://github.com/cloudflare/cloudflared/releases"
    exit 1
}

Write-Host "Starting Cloudflare Quick Tunnel to http://localhost:$HttpPort ..."
cloudflared tunnel --url "http://localhost:$HttpPort"
