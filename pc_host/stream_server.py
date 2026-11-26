import argparse
import asyncio
import glob
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from typing import Optional

import cv2
import numpy as np
import serial
import uvicorn
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse

IMG_SIZE = 224


def detect_serial_port() -> Optional[str]:
    if os.name == "nt":
        return "YOUR_COM_PORT"
    ports = sorted(
        glob.glob("/dev/cu.usbmodem*")
        + glob.glob("/dev/cu.usbserial*")
        + glob.glob("/dev/cu.wchusbserial*")
        + glob.glob("/dev/cu.SLAB*")
    )
    return ports[0] if ports else None


class StreamState:
    def __init__(
        self,
        com_port: Optional[str],
        baud_rate: int,
        camera_index: int,
        stream_fps: float,
        jpeg_quality: int,
    ):
        self.configured_port = com_port
        self.baud_rate = baud_rate
        self.camera_index = camera_index
        self.stream_fps = max(1.0, stream_fps)
        self.jpeg_quality = int(np.clip(jpeg_quality, 10, 95))

        self.lock = threading.Lock()
        self.running = True
        self.started_at = time.time()

        # Shared camera / stream state
        self.camera_connected = False
        self.latest_jpeg: Optional[bytes] = None
        self.frame_seq = 0

        # Shared ESP32 serial state
        self.latest_payload: Optional[bytes] = None
        self.esp_connected = False
        self.esp_port: Optional[str] = None
        self.esp_fps = 0.0
        self.latest_boxes: list[tuple[float, int, int, int, int]] = []
        self.last_inference_at: Optional[float] = None
        self.last_error: Optional[str] = None

        self._threads: list[threading.Thread] = []

    def start(self):
        self.running = True
        self._threads = [
            threading.Thread(target=self._serial_worker, name="esp32-serial", daemon=True),
            threading.Thread(target=self._camera_worker, name="webcam-capture", daemon=True),
        ]
        for t in self._threads:
            t.start()

    def stop(self):
        self.running = False
        for t in self._threads:
            t.join(timeout=2.0)

    def _serial_worker(self):
        while self.running:
            port = self.configured_port or detect_serial_port()
            if not port:
                with self.lock:
                    self.esp_connected = False
                    self.esp_port = None
                    self.esp_fps = 0.0
                    self.last_error = "No ESP32 USB serial port found"
                time.sleep(2.0)
                continue

            ser: Optional[serial.Serial] = None
            try:
                ser = serial.Serial()
                ser.port = port
                ser.baudrate = self.baud_rate
                ser.timeout = 0.05
                ser.write_timeout = 3.0
                ser.dsrdtr = False
                ser.rtscts = False
                ser.open()
                ser.dtr = False
                ser.rts = False

                print(f"[ESP32] Connected on {port} @ {self.baud_rate} baud; waiting for boot...")
                time.sleep(2.5)
                ser.reset_input_buffer()
                ser.reset_output_buffer()

                with self.lock:
                    self.esp_connected = True
                    self.esp_port = port
                    self.last_error = None

                last_infer_time = time.time()

                while self.running:
                    payload_to_send = None
                    with self.lock:
                        if self.latest_payload is not None:
                            payload_to_send = self.latest_payload
                            self.latest_payload = None

                    if payload_to_send is None:
                        time.sleep(0.01)
                        continue

                    try:
                        ser.write(payload_to_send)
                        ser.flush()
                    except serial.SerialTimeoutException:
                        ser.reset_output_buffer()
                        continue

                    deadline = time.time() + 0.6
                    new_boxes: list[tuple[float, int, int, int, int]] = []
                    got_response = False

                    while time.time() < deadline and self.running:
                        if ser.in_waiting:
                            line = ser.readline().decode("utf-8", errors="ignore").strip()
                            if not line:
                                continue
                            if line == "RES:NONE":
                                got_response = True
                                break
                            elif line.startswith("RES:PIGEON"):
                                parts = line.split(",")
                                if len(parts) == 6:
                                    try:
                                        score = float(parts[1])
                                        x1, y1, x2, y2 = map(int, parts[2:6])
                                        new_boxes.append((score, x1, y1, x2, y2))
                                        got_response = True
                                    except ValueError:
                                        pass
                                time.sleep(0.002)
                                if not ser.in_waiting:
                                    break
                        else:
                            time.sleep(0.002)

                    if got_response:
                        now = time.time()
                        dt = now - last_infer_time
                        last_infer_time = now
                        with self.lock:
                            self.latest_boxes = new_boxes
                            self.esp_fps = 1.0 / dt if dt > 0 else 0.0
                            self.last_inference_at = now

            except (serial.SerialException, OSError) as exc:
                print(f"[ESP32] Connection error on {port}: {exc}")
                with self.lock:
                    self.esp_connected = False
                    self.esp_fps = 0.0
                    self.latest_boxes = []
                    self.last_error = str(exc)
                time.sleep(2.0)
            finally:
                if ser is not None and ser.is_open:
                    try:
                        ser.close()
                    except Exception:
                        pass

    def _open_camera(self) -> cv2.VideoCapture:
        if os.name == "nt":
            cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        elif sys.platform == "darwin":
            cap = cv2.VideoCapture(self.camera_index, cv2.CAP_AVFOUNDATION)
        else:
            cap = cv2.VideoCapture(self.camera_index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _camera_worker(self):
        frame_interval = 1.0 / self.stream_fps
        last_encode_time = 0.0

        while self.running:
            cap = self._open_camera()
            if not cap.isOpened():
                print(f"[CAM] Cannot open camera index {self.camera_index}; retrying in 2s...")
                with self.lock:
                    self.camera_connected = False
                cap.release()
                time.sleep(2.0)
                continue

            print(f"[CAM] Webcam {self.camera_index} opened (640x480)")
            with self.lock:
                self.camera_connected = True

            consecutive_failures = 0
            try:
                while self.running:
                    ret, frame = cap.read()
                    if not ret:
                        consecutive_failures += 1
                        if consecutive_failures >= 30:
                            print("[CAM] Too many read failures; reopening camera...")
                            break
                        time.sleep(0.02)
                        continue
                    consecutive_failures = 0

                    with self.lock:
                        need_frame = self.esp_connected and (self.latest_payload is None)
                        boxes_copy = list(self.latest_boxes)
                        current_esp_fps = self.esp_fps
                        esp_ok = self.esp_connected

                    if need_frame:
                        resized = cv2.resize(frame, (IMG_SIZE, IMG_SIZE))
                        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.uint16)
                        r = (rgb[:, :, 0] >> 3) << 11
                        g = (rgb[:, :, 1] >> 2) << 5
                        b = rgb[:, :, 2] >> 3
                        rgb565 = (r | g | b).astype(">u2").tobytes()
                        with self.lock:
                            self.latest_payload = b"\xAA\x55" + rgb565

                    now = time.time()
                    if now - last_encode_time < frame_interval:
                        continue
                    last_encode_time = now

                    h, w, _ = frame.shape
                    scale_x = w / IMG_SIZE
                    scale_y = h / IMG_SIZE

                    for (score, x1, y1, x2, y2) in boxes_copy:
                        bx1, by1 = int(x1 * scale_x), int(y1 * scale_y)
                        bx2, by2 = int(x2 * scale_x), int(y2 * scale_y)
                        cv2.rectangle(frame, (bx1, by1), (bx2, by2), (0, 255, 0), 2)
                        cv2.putText(
                            frame,
                            f"Pigeon {score:.2f}",
                            (bx1, max(20, by1 - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (0, 255, 0),
                            2,
                        )

                    status_text = (
                        f"ESP32 AI: {current_esp_fps:.2f} FPS | Birds: {len(boxes_copy)}"
                        if esp_ok
                        else "ESP32: Connecting..."
                    )
                    status_color = (0, 255, 255) if esp_ok else (0, 128, 255)
                    cv2.putText(
                        frame,
                        status_text,
                        (10, 28),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        status_color,
                        2,
                    )

                    ok, encoded = cv2.imencode(
                        ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
                    )
                    if ok:
                        jpeg_bytes = encoded.tobytes()
                        with self.lock:
                            self.latest_jpeg = jpeg_bytes
                            self.frame_seq += 1
            finally:
                cap.release()
                with self.lock:
                    self.camera_connected = False

    def get_status(self) -> dict:
        with self.lock:
            detections = [
                {"score": round(score, 3), "box": [x1, y1, x2, y2]}
                for (score, x1, y1, x2, y2) in self.latest_boxes
            ]
            return {
                "camera_connected": self.camera_connected,
                "esp_connected": self.esp_connected,
                "esp_port": self.esp_port,
                "esp_fps": round(self.esp_fps, 2),
                "count": len(detections),
                "detected": len(detections) > 0,
                "detections": detections,
                "last_inference_at": self.last_inference_at,
                "last_error": self.last_error,
                "uptime_sec": round(time.time() - self.started_at, 1),
            }


def create_app(state: StreamState) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        state.start()
        try:
            yield
        finally:
            state.stop()

    app = FastAPI(title="BirdML Live Stream Host", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>BirdML Live Stream</title>
  <style>
    body { font-family: system-ui, sans-serif; background: #111; color: #eee; text-align: center; padding: 24px; }
    img { max-width: 100%; width: 640px; border-radius: 12px; border: 1px solid #333; background: #000; }
    pre { max-width: 640px; margin: 16px auto; text-align: left; background: #1c1c1c; padding: 12px; border-radius: 8px; }
  </style>
</head>
<body>
  <h2>BirdML Live Detection Stream</h2>
  <img src="/video_feed" alt="Live Stream" />
  <pre id="status">Loading status...</pre>
  <script>
    async function poll() {
      try {
        const res = await fetch('/status');
        const data = await res.json();
        document.getElementById('status').textContent = JSON.stringify(data, null, 2);
      } catch (e) {
        document.getElementById('status').textContent = 'Error: ' + e;
      }
    }
    poll();
    setInterval(poll, 1000);
  </script>
</body>
</html>"""

    @app.get("/video_feed")
    async def video_feed():
        async def frame_generator():
            last_seq = -1
            while state.running:
                with state.lock:
                    seq = state.frame_seq
                    jpeg = state.latest_jpeg
                if jpeg is not None and seq != last_seq:
                    last_seq = seq
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Cache-Control: no-cache\r\n\r\n"
                        + jpeg
                        + b"\r\n"
                    )
                else:
                    await asyncio.sleep(0.02)

        return StreamingResponse(
            frame_generator(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
        )

    @app.get("/snapshot.jpg")
    async def snapshot():
        with state.lock:
            jpeg = state.latest_jpeg
        if jpeg is None:
            return Response(status_code=503, content=b"Camera frame not ready")
        return Response(
            content=jpeg,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/status")
    async def status():
        return state.get_status()

    return app


def parse_args():
    parser = argparse.ArgumentParser(description="BirdML Webcam + ESP32-S3 Live Stream Server")
    parser.add_argument(
        "--port",
        default=os.getenv("SMARTBIRD_COM_PORT") or None,
        help="ESP32 serial port (default: auto-detect)",
    )
    parser.add_argument("--baud", type=int, default=2000000, help="ESP32 UART baud rate")
    parser.add_argument(
        "--camera",
        type=int,
        default=int(os.getenv("SMARTBIRD_CAMERA_INDEX", "0")),
        help="OpenCV webcam index (default: 0)",
    )
    parser.add_argument("--host", default="0.0.0.0", help="HTTP bind host (default: 0.0.0.0)")
    parser.add_argument("--http-port", type=int, default=8000, help="HTTP port (default: 8000)")
    parser.add_argument("--stream-fps", type=float, default=15.0, help="Max MJPEG stream FPS")
    parser.add_argument("--jpeg-quality", type=int, default=75, help="JPEG quality 10-95")
    return parser.parse_args()


def main():
    args = parse_args()
    state = StreamState(
        com_port=args.port,
        baud_rate=args.baud,
        camera_index=args.camera,
        stream_fps=args.stream_fps,
        jpeg_quality=args.jpeg_quality,
    )
    app = create_app(state)
    print(f"Starting BirdML stream server at http://localhost:{args.http_port}")
    uvicorn.run(app, host=args.host, port=args.http_port, log_level="info")


if __name__ == "__main__":
    main()
