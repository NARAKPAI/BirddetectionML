#!/usr/bin/env python3
"""
Auto-sync Cloudflare Quick Tunnel URL to Firebase RTDB
Run this on your PC host machine instead of plain start_tunnel.sh.
It starts cloudflared, captures the generated https://*.trycloudflare.com URL,
and writes it directly to Firebase Realtime Database at /birdml/streamUrl.
"""

import sys
import re
import time
import subprocess
import json
import urllib.request
import urllib.error

DEFAULT_PORT = 8000
FIREBASE_DB_URL = "https://embeded-project-fc70e-default-rtdb.asia-southeast1.firebasedatabase.app"
FIREBASE_PATH = "birdml/streamUrl.json"

def sync_url_to_firebase(url: str):
    target = f"{FIREBASE_DB_URL}/{FIREBASE_PATH}"
    print(f"\n[Firebase Sync] Writing live stream URL to RTDB: {url}")
    data = json.dumps(url).encode("utf-8")
    req = urllib.request.Request(
        target,
        data=data,
        headers={"Content-Type": "application/json"},
        method="PUT"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                print(f"[Firebase Sync] Successfully synced! Dashboard viewers will auto-connect.")
            else:
                print(f"[Firebase Sync] Response HTTP {resp.status}")
    except Exception as exc:
        print(f"[Firebase Sync] Failed to update Firebase RTDB: {exc}")

def main():
    port = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT_PORT)
    cmd = ["cloudflared", "tunnel", "--url", f"http://localhost:{port}"]

    print(f"=======================================================")
    print(f" Starting Cloudflare Tunnel & Firebase RTDB Auto-Sync  ")
    print(f" Target: http://localhost:{port}                       ")
    print(f"=======================================================\n")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
    except FileNotFoundError:
        print("Error: 'cloudflared' command not found in PATH.")
        print("Please install cloudflared first: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/")
        sys.exit(1)

    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
    synced = False

    try:
        for line in iter(process.stdout.readline, ""):
            print(line, end="", flush=True)
            if not synced:
                match = url_pattern.search(line)
                if match:
                    tunnel_url = match.group(0)
                    sync_url_to_firebase(tunnel_url)
                    synced = True
    except KeyboardInterrupt:
        print("\nStopping tunnel...")
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()

if __name__ == "__main__":
    main()
