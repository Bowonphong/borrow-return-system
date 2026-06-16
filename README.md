# 📦 ระบบยืม-คืนของ (Borrow & Return System)

ระบบยืม-คืนของแบบ offline ทำงานบนโน๊ตบุ๊คเครื่องเดียว  
รองรับ Windows 10/11 และ Linux (Ubuntu 20.04+)

---

## โครงสร้างโฟลเดอร์

```
borrow-return-system/
├── main.py              ← FastAPI backend (entry point)
├── database.py          ← SQLite operations
├── face_manager.py      ← Webcam + face recognition
├── ha_integration.py    ← Home Assistant (REST/MQTT)
├── config.py            ← การตั้งค่าทั้งหมด
├── requirements.txt     ← Python dependencies
├── static/
│   └── index.html       ← Web UI (single page)
└── data/                ← สร้างอัตโนมัติตอนรัน
    ├── borrow.db        ← ฐานข้อมูล SQLite
    └── faces/           ← ภาพใบหน้าผู้ใช้
```

---

## ขั้นตอนติดตั้ง

### 1. ติดตั้ง Python 3.10+

**Windows:** ดาวน์โหลดจาก https://python.org  
**Linux:** `sudo apt install python3 python3-pip python3-venv`

### 2. สร้าง Virtual Environment

```bash
# เข้าไปใน folder
cd borrow-return-system

# สร้าง venv
python -m venv venv

# Activate
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
```

### 3. ติดตั้ง face_recognition (สำคัญ — ทำก่อน pip install)

#### Windows

```bash
# ติดตั้ง CMake ก่อน
pip install cmake

# ติดตั้ง dlib (pre-built wheel เร็วกว่า)
pip install https://github.com/jloh02/dlib/releases/download/v19.22/dlib-19.22.99-cp310-cp310-win_amd64.whl

# ถ้า Python 3.11 ใช้:
# pip install dlib --find-links https://github.com/z-mahmud22/Dlib_Windows_Python3.x/releases

# ติดตั้ง face_recognition
pip install face_recognition
```

#### Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install -y build-essential cmake python3-dev
sudo apt install -y libopenblas-dev liblapack-dev libx11-dev

pip install dlib face_recognition
```

### 4. ติดตั้ง Dependencies ที่เหลือ

```bash
pip install fastapi uvicorn[standard] opencv-python numpy requests paho-mqtt
```

หรือใช้ requirements.txt:

```bash
pip install -r requirements.txt
```

---

## การตั้งค่า config.py

เปิดไฟล์ `config.py` และแก้ไข:

```python
CAMERA_INDEX = 0        # 0 = กล้องแรก, 1 = กล้องที่สอง
                        # ถ้า Logitech ไม่เจอ ลอง 1 หรือ 2
```

---

## เชื่อมต่อ Home Assistant

### วิธีที่ 1: REST API (แนะนำ)

1. เปิด Home Assistant → โปรไฟล์ → **Long-Lived Access Tokens** → สร้าง token
2. แก้ `config.py`:

```python
HA_ENABLED = True
HA_URL     = "http://192.168.1.xxx:8123"   # IP ของ HA
HA_TOKEN   = "eyJhbGciOiJIUzI1NiIs..."    # Token ที่ได้
```

3. เพิ่ม Sensor ใน `configuration.yaml` ของ HA:

```yaml
# configuration.yaml
template:
  - sensor:
      - name: "Borrow Last Action"
        unique_id: borrow_last_action
        state: "{{ states('sensor.borrow_last_action') }}"
      - name: "Borrow Total Borrowed"
        unique_id: borrow_total_borrowed
        state: "{{ states('sensor.borrow_total_borrowed') }}"
```

4. เพิ่ม Automation ตัวอย่าง:

```yaml
# automations.yaml
- alias: "แจ้งเตือนเมื่อยืมของ"
  trigger:
    - platform: event
      event_type: borrow_system_borrow
  action:
    - service: notify.notify
      data:
        message: >
          {{ trigger.event.data.user_name }} ยืม {{ trigger.event.data.item_name }}
```

### วิธีที่ 2: MQTT

1. ติดตั้ง Mosquitto broker ใน HA (HACS หรือ Add-on Store)
2. แก้ `config.py`:

```python
MQTT_ENABLED   = True
MQTT_HOST      = "localhost"   # หรือ IP ของ HA
MQTT_PORT      = 1883
MQTT_USER      = "mqtt_user"
MQTT_PASSWORD  = "mqtt_pass"
```

3. Topics ที่ระบบส่ง:
   - `borrow_system/borrow` — เมื่อมีการยืม
   - `borrow_system/return` — เมื่อมีการคืน
   - `borrow_system/status/total_borrowed` — จำนวนที่ยืมอยู่

4. ใน HA `configuration.yaml`:

```yaml
mqtt:
  sensor:
    - name: "Total Borrowed"
      state_topic: "borrow_system/status/total_borrowed"
      value_template: "{{ value_json.value }}"
```

---

## วิธีรันระบบ

```bash
# Activate venv ก่อน
venv\Scripts\activate        # Windows
source venv/bin/activate     # Linux

# รันระบบ
python main.py
```

เปิด browser ที่ **http://localhost:8000**

---

## วิธีใช้งาน

### การยืมของ
1. ไปแท็บ **ยืมของ**
2. กด **ดูตัวอย่าง** เพื่อเปิดกล้อง
3. กด **จดจำใบหน้า** — ให้ผู้ยืมมองตรงกล้อง
   - (หรือเลือกผู้ใช้เองจาก dropdown ถ้า face recognition ยังไม่ได้ตั้งค่า)
4. สแกนบาร์โค้ดสิ่งของในช่อง (Scanner พิมพ์ค่าอัตโนมัติ → กด Enter)
5. กด **บันทึกการยืม**

### การคืนของ
**ผ่านบาร์โค้ด:** สแกนบาร์โค้ดสิ่งของ → กด คืนของ  
**ผ่านใบหน้า:** สแกนใบหน้า → ระบบแสดงรายการที่ยืม → เลือกกด คืน

### เพิ่มผู้ใช้
1. แท็บ **ผู้ใช้** → ใส่ชื่อ → กด **เพิ่มผู้ใช้**
2. ให้ผู้ใช้มองตรงกล้อง (ระบบจะจับภาพอัตโนมัติ)

### เพิ่มสิ่งของ
แท็บ **สิ่งของ** → สแกนบาร์โค้ด → ใส่ชื่อ → **เพิ่มสิ่งของ**

---

## แก้ปัญหาที่พบบ่อย

| ปัญหา | วิธีแก้ |
|-------|---------|
| กล้องไม่เปิด | เปลี่ยน `CAMERA_INDEX = 1` ใน config.py |
| face_recognition ติดตั้งไม่ได้ | ดูขั้นตอน Windows/Linux ด้านบน |
| บาร์โค้ด Scanner ไม่ทำงาน | คลิก input field ก่อนสแกน (Scanner ส่งค่าเหมือน keyboard) |
| HA ไม่ตอบสนอง | ตรวจสอบ IP, port 8123, และ Token |
| port 8000 ถูกใช้งาน | แก้ `PORT = 8001` ใน config.py |

---

## รัน Auto-start (Linux systemd)

```ini
# /etc/systemd/system/borrow-system.service
[Unit]
Description=Borrow Return System
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/borrow-return-system
ExecStart=/home/pi/borrow-return-system/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable borrow-system
sudo systemctl start borrow-system
```
