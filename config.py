# ============================================================
#  Borrow & Return System — Configuration
# ============================================================

# --- Camera ---
CAMERA_INDEX = 0          # เปลี่ยนถ้ามีกล้องหลายตัว (0, 1, 2 ...)
FACE_RECOGNITION_TOLERANCE = 0.55   # ยิ่งน้อยยิ่งเข้มงวด (0.4–0.65)
FACE_CAPTURE_ATTEMPTS = 40          # จำนวนเฟรมที่พยายามจับใบหน้า

# --- Paths ---
DB_PATH    = "data/borrow.db"
FACES_DIR  = "data/faces"

# --- Home Assistant (REST API) ---
HA_ENABLED = False          # เปลี่ยนเป็น True เมื่อตั้งค่าเสร็จ
HA_URL     = "http://localhost:8123"   # URL ของ Home Assistant
HA_TOKEN   = "eyJ..."                  # Long-Lived Access Token จาก HA

# --- MQTT (ทางเลือกแทน REST) ---
MQTT_ENABLED       = False
MQTT_HOST          = "localhost"   # IP ของ MQTT Broker (Mosquitto)
MQTT_PORT          = 1883
MQTT_USER          = ""
MQTT_PASSWORD      = ""
MQTT_TOPIC_PREFIX  = "borrow_system"

# --- Web Server ---
HOST = "0.0.0.0"
PORT = 8000
