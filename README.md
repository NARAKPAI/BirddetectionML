# SmartBirdRepellent - Bird Detection System

ระบบตรวจจับนกพิราบและขับไล่นกอัตโนมัติ โดยแบ่งการทำงานแบบ Edge Offloading:
- **PC Host (กล้อง & เซิร์ฟเวอร์):** ดึงภาพจาก Webcam, ย่อขนาดภาพเป็น 224x224 (RGB565) และส่งผ่าน Serial UART ไปยังบอร์ด ESP32-S3 พร้อมแสดงผลผ่าน Web Dashboard หรือหน้าต่าง GUI
- **ESP32-S3 (Edge AI):** ประมวลผลโมเดล Deep Learning (ESP-DL / Pico Object Detection) บนชิป ESP32 แล้วส่งพิกัด Bounding Box และคะแนนความมั่นใจกลับมาที่ PC

---

## สารบัญ
1. [ข้อกำหนดเบื้องต้น (Prerequisites)](#1-ข้อกำหนดเบื้องต้น-prerequisites)
2. [การติดตั้ง Dependencies](#2-การติดตั้ง-dependencies)
3. [การเตรียมบอร์ด ESP32 และกล้อง](#3-การเตรียมบอร์ด-esp32-และกล้อง)
4. [วิธีรัน PC Host](#4-วิธีรัน-pc-host)
   - [แบบที่ 1: Web Stream Server (แนะนำ)](#แบบที่-1-web-stream-server-แนะนำ)
   - [แบบที่ 2: Desktop GUI Window](#แบบที่-2-desktop-gui-window)
5. [พารามิเตอร์และตัวเลือก (CLI Options)](#5-พารามิเตอร์และตัวเลือก-cli-options)
6. [การรีโมตดูผลผ่าน Internet (Cloudflare Tunnel)](#6-การรีโมตดูผลผ่าน-internet-cloudflare-tunnel)
7. [การแก้ไขปัญหาเบื้องต้น (Troubleshooting)](#7-การแก้ไขปัญหาเบื้องต้น-troubleshooting)

---

## 1. ข้อกำหนดเบื้องต้น (Prerequisites)

- **Python:** เวอร์ชัน 3.10 ขึ้นไป
- **Hardware:**
  - บอร์ด **ESP32-S3** ที่แฟลชเฟิร์มแวร์ `pigeon_detect` เรียบร้อยแล้ว เชื่อมต่อผ่านสาย USB
  - กล้อง **USB Webcam** หรือกล้องโน้ตบุ๊ก

---

## 2. การติดตั้ง Dependencies

เปิด Terminal / PowerShell ในโฟลเดอร์โปรเจกต์ `BirddetectionML`:

### บน Windows:
```powershell
# 1. สร้าง Virtual Environment (ถ้ายังไม่มี)
python -m venv venv

# 2. เปิดใช้งาน Virtual Environment
.\venv\Scripts\activate

# 3. ติดตั้งไลบรารีที่จำเป็น
pip install -r requirements.txt
```

### บน macOS / Linux:
```bash
# 1. สร้าง Virtual Environment
python3 -m venv venv

# 2. เปิดใช้งาน Virtual Environment
source venv/bin/activate

# 3. ติดตั้งไลบรารีที่จำเป็น
pip install -r requirements.txt
```

> **ไลบรารีหลักที่ใช้งาน:** `opencv-python`, `numpy`, `pyserial`, `fastapi`, `uvicorn`

---

## 3. การเตรียมบอร์ด ESP32 และกล้อง

1. เสียบสาย USB ระหว่างคอมพิวเตอร์กับ ESP32-S3
2. ตรวจสอบพอร์ต Serial (COM Port / Device Port):
   - **Windows (PowerShell):** รันคำสั่งนี้เพื่อดูชื่อพอร์ตทันที:
     ```powershell
     [System.IO.Ports.SerialPort]::GetPortNames()
     ```
     หรือกด `Win + X` -> เลือก **Device Manager** -> ดูที่หัวข้อ **Ports (COM & LPT)** (เช่น `COM5`, `COM8`)
   - **macOS / Linux:** ใช้คำสั่ง `ls /dev/cu.usb*` หรือ `ls /dev/ttyUSB*`
3. ค่า Baud Rate เริ่มต้นของโปรเจกต์นี้คือ **`2000000` (2 Mbps)**

---

## 4. วิธีรัน PC Host

เข้าไปที่โฟลเดอร์ `pc_host` หรือรันจากรูทโปรเจกต์:

### แบบที่ 1: Web Stream Server (แนะนำ)
สคริปต์ [pc_host/stream_server.py](file:///C:/Build/cedt/embeded_project/BirddetectionML/pc_host/stream_server.py) จะเปิด Web Dashboard ที่แสดงภาพสตรีมแบบเรียลไทม์ พร้อม Bounding Box, FPS, สถานะการเชื่อมต่อ และบันทึกประวัติการตรวจจับ

```powershell
# รันด้วยค่า default (พอร์ต COM8 บน Windows, กล้องตัวแรก index 0, Web Port 8000)
python pc_host/stream_server.py

# หรือระบุ COM Port และเลือกกล้องด้วยตนเอง
python pc_host/stream_server.py --port COM8 --camera 0 --http-port 8000
```

เมื่อเซิร์ฟเวอร์เริ่มทำงาน ให้เปิดเว็บบราวเซอร์ไปที่:
👉 **[http://localhost:8000](http://localhost:8000)**

#### Endpoint ต่างๆ ที่ให้บริการ:
- `/` : หน้า Web Dashboard (แสดงวิดีโอสด, FPS, สถานะ ESP32, ตาราง Event Log)
- `/video_feed` : MJPEG Video Stream สำหรับนำไปฝังในเว็บอื่น
- `/snapshot.jpg` : รูปภาพ JPEG ล่าสุด
- `/status` : ข้อมูลสถานะระบบในรูปแบบ JSON

---

### แบบที่ 2: Desktop GUI Window
สคริปต์ [pc_host/stream_pc.py](file:///C:/Build/cedt/embeded_project/BirddetectionML/pc_host/stream_pc.py) จะเปิดหน้าต่าง OpenCV บนหน้าจอคอมพิวเตอร์โดยตรง เหมาะสำหรับการทดสอบหน้าเครื่องอย่างรวดเร็ว

```powershell
# บน Windows (กำหนดพอร์ตผ่าน Environment Variable หากไม่ได้ใช้ COM8)
$env:SMARTBIRD_COM_PORT="COM8"
python pc_host/stream_pc.py

# บน macOS / Linux
export SMARTBIRD_COM_PORT="/dev/cu.usbmodem1101"
python pc_host/stream_pc.py
```
*💡 กดปุ่ม **`q`** บนหน้าต่างวิดีโอเพื่อปิดโปรแกรม*

---

## 5. พารามิเตอร์และตัวเลือก (CLI Options)

สคริปต์ `stream_server.py` รองรับอาร์กิวเมนต์คำสั่งดังต่อไปนี้:

| Argument | ค่าเริ่มต้น (Default) | คำอธิบาย |
| :--- | :--- | :--- |
| `--port` | Auto-detect (COM8 บน Win) | Serial Port ของ ESP32 (เช่น `COM8`, `/dev/ttyUSB0`) |
| `--baud` | `2000000` | Baud Rate ของ Serial UART (ต้องตรงกับ firmware) |
| `--camera` | `0` | Index ของกล้อง Webcam (0 = กล้องหลัก, 1 = กล้องเสริม) |
| `--host` | `0.0.0.0` | Bind IP Address สำหรับ Web Server |
| `--http-port` | `8000` | พอร์ตสำหรับเปิด Web Dashboard |
| `--stream-fps` | `15.0` | อัตราเฟรมเรตสูงสุดในการสตรีมภาพผ่านเว็บ |
| `--jpeg-quality` | `75` | คุณภาพของภาพ JPEG สตรีม (10 - 95) |

ตัวอย่างการรันแบบปรับแต่งเต็มรูปแบบ:
```powershell
python pc_host/stream_server.py --port COM5 --baud 2000000 --camera 1 --http-port 8080 --stream-fps 20
```

---

## 6. การรีโมตดูผลผ่าน Internet (Cloudflare Tunnel)

หากต้องการเปิดให้เครื่องอื่นภายนอกเครือข่ายเข้าดู Web Dashboard ได้ สามารถใช้ Cloudflare Tunnel ผ่านสคริปต์ `start_tunnel.sh`:

### บน Windows:
```powershell
powershell -ExecutionPolicy Bypass -File pc_host/start_tunnel.ps1 8000
```

### บน macOS / Linux:
```bash
bash pc_host/start_tunnel.sh 8000
```
ระบบจะสร้าง URL แบบชั่วคราว เช่น `https://xxxx.trycloudflare.com` สำหรับนำไปเปิดบนมือถือหรือเครือข่ายภายนอก

---

## 7. การแก้ไขปัญหาเบื้องต้น (Troubleshooting)

1. **`Cannot open webcam` / หน้าจอไม่ขึ้นภาพกล้อง:**
   - ตรวจสอบว่ามีโปรแกรมอื่นเปิดกล้องค้างไว้หรือไม่ (เช่น Zoom, Teams, Camera app)
   - ลองเปลี่ยน index กล้อง เช่น `--camera 1` หรือ `--camera 2`

2. **`Could not open port COM...` / Permission Error:**
   - ตรวจสอบว่าปิด Serial Monitor อื่นๆ เช่น ESP-IDF Monitor, Arduino IDE, PuTTY ก่อนรันสคริปต์
   - ถอดสาย USB เสียบใหม่ หรือตรวจดูหมายเลขพอร์ตใน Device Manager ให้ถูกต้อง

3. **ESP32 ไม่ตอบกลับ หรือขึ้นสถานะ Disconnected:**
   - ตรวจสอบค่า Baud rate (ต้องเป็น `2000000`)
   - กดปุ่ม `EN` / `RST` บนบอร์ด ESP32 เพื่อรีเซ็ตบอร์ดใหม่
   - ตรวจสอบว่าโปรเจกต์ในบอร์ด ESP32 แฟลชเฟิร์มแวร์ตรวจจับนกเรียบร้อยและกำลังรอรับภาพผ่าน UART
