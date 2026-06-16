"""
face_manager.py — Webcam capture + face recognition
ใช้ face_recognition library (dlib-based) หรือ fallback OpenCV Haar Cascade
"""

import cv2
import numpy as np
import os
import pickle
import base64
from datetime import datetime
from config import CAMERA_INDEX, FACE_RECOGNITION_TOLERANCE, FACE_CAPTURE_ATTEMPTS, FACES_DIR
import database as db
from io import BytesIO

# ─── Optional face_recognition import ──────────────────────
try:
    import face_recognition as fr
    FR_AVAILABLE = True
except ImportError:
    FR_AVAILABLE = False
    print("[WARN] face_recognition ไม่ได้ติดตั้ง — ใช้ OpenCV Haar Cascade แทน")

# ─── Haar Cascade (fallback) ────────────────────────────────
_cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
_face_cascade = cv2.CascadeClassifier(_cascade_path)


def ensure_dirs():
    os.makedirs(FACES_DIR, exist_ok=True)


# ─────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────
def _open_camera() -> cv2.VideoCapture:
    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    return cap


def _has_face_haar(frame: np.ndarray) -> bool:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = _face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
    return len(faces) > 0


def _encode_face_fr(frame: np.ndarray):
    """ใช้ face_recognition library เพื่อ encode ใบหน้า"""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    locs = fr.face_locations(rgb, model="hog")
    if not locs:
        return None
    encs = fr.face_encodings(rgb, locs)
    return encs[0] if encs else None


# ─────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────
def capture_frame_as_base64() -> str | None:
    """ถ่ายภาพ 1 เฟรมจากกล้อง คืนค่า base64 JPEG"""
    cap = _open_camera()
    result = None
    for _ in range(5):          # warm-up frames
        ret, frame = cap.read()
        if ret:
            result = frame
    cap.release()
    if result is None:
        return None
    _, buf = cv2.imencode(".jpg", result, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(buf).decode()


def add_user_face(name: str) -> tuple[int | None, str]:
    """
    เปิดกล้อง, จับใบหน้า, บันทึกภาพ + encoding ลง DB
    คืนค่า (user_id, message)
    """
    ensure_dirs()
    cap = _open_camera()
    encoding = None
    saved_frame = None

    for _ in range(FACE_CAPTURE_ATTEMPTS):
        ret, frame = cap.read()
        if not ret:
            continue
        if FR_AVAILABLE:
            enc = _encode_face_fr(frame)
            if enc is not None:
                encoding = enc
                saved_frame = frame.copy()
                break
        else:
            if _has_face_haar(frame):
                saved_frame = frame.copy()
                break

    cap.release()

    if saved_frame is None:
        return None, "ไม่พบใบหน้าในกล้อง กรุณาลองใหม่และมองตรงกล้อง"

    # บันทึกภาพ
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in name)
    img_path = os.path.join(FACES_DIR, f"{safe_name}_{ts}.jpg")
    cv2.imwrite(img_path, saved_frame)

    enc_bytes = pickle.dumps(encoding) if encoding is not None else None
    uid = db.add_user(name, enc_bytes, img_path)
    return uid, "success"


def recognize_face() -> tuple[dict | None, str]:
    """
    เปิดกล้อง, พยายามจดจำใบหน้า, คืนค่า user dict หรือ None
    """
    users = db.get_all_users_with_encodings()
    if not users:
        return None, "ยังไม่มีข้อมูลใบหน้าในระบบ"

    if not FR_AVAILABLE:
        return None, "face_recognition ไม่ได้ติดตั้ง — ไม่สามารถจดจำใบหน้าได้"

    # โหลด known encodings
    known_encs, known_ids, known_names = [], [], []
    for u in users:
        if u["face_encoding"]:
            known_encs.append(pickle.loads(u["face_encoding"]))
            known_ids.append(u["id"])
            known_names.append(u["name"])

    if not known_encs:
        return None, "ยังไม่มีข้อมูลใบหน้า"

    cap = _open_camera()
    for _ in range(FACE_CAPTURE_ATTEMPTS):
        ret, frame = cap.read()
        if not ret:
            continue

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        locs = fr.face_locations(rgb, model="hog")
        if not locs:
            continue

        encs = fr.face_encodings(rgb, locs)
        for enc in encs:
            matches = fr.compare_faces(known_encs, enc, tolerance=FACE_RECOGNITION_TOLERANCE)
            dists = fr.face_distance(known_encs, enc)
            best = int(np.argmin(dists))
            if matches[best]:
                cap.release()
                return {
                    "id": known_ids[best],
                    "name": known_names[best],
                    "confidence": round(float(1 - dists[best]) * 100, 1),
                }, "success"

    cap.release()
    return None, "ไม่สามารถจดจำใบหน้าได้ กรุณาลองใหม่"


def recognize_face_from_frame(image_base64: str) -> tuple[dict | None, str]:
    """
    จดจำใบหน้าจากภาพ base64 ที่ส่งมาจาก browser (WebRTC frame)
    ไม่ต้องเปิดกล้อง backend
    คืนค่า (user_dict, message)
    """
    users = db.get_all_users_with_encodings()
    if not users:
        return None, "ยังไม่มีข้อมูลใบหน้าในระบบ"

    if not FR_AVAILABLE:
        return None, "face_recognition ไม่ได้ติดตั้ง"

    # โหลด known encodings
    known_encs, known_ids, known_names = [], [], []
    for u in users:
        if u["face_encoding"]:
            try:
                known_encs.append(pickle.loads(u["face_encoding"]))
                known_ids.append(u["id"])
                known_names.append(u["name"])
            except Exception:
                continue

    if not known_encs:
        return None, "ยังไม่มีข้อมูลใบหน้าในฐานข้อมูล"

    try:
        # ถอด base64 → RGB numpy array — ใช้ PIL เพื่อรองรับ PNG/RGBA/EXIF ทุกฟอร์แมต
        from PIL import Image
        img_bytes = base64.b64decode(image_base64.strip())
        pil_img   = Image.open(BytesIO(img_bytes)).convert('RGB')
        rgb = np.array(pil_img, dtype=np.uint8)

        locs = fr.face_locations(rgb, model="hog")
        if not locs:
            return None, "ไม่พบใบหน้าในภาพ"

        encs = fr.face_encodings(rgb, locs)
        for enc in encs:
            matches = fr.compare_faces(known_encs, enc, tolerance=FACE_RECOGNITION_TOLERANCE)
            dists   = fr.face_distance(known_encs, enc)
            best    = int(np.argmin(dists))
            if matches[best]:
                return {
                    "id":         known_ids[best],
                    "name":       known_names[best],
                    "confidence": round(float(1 - dists[best]) * 100, 1),
                }, "success"

        return None, "ไม่สามารถจดจำใบหน้าได้"
    except Exception as e:
        return None, f"เกิดข้อผิดพลาด: {str(e)}"


def add_user_face_from_image(name: str, image_base64: str) -> tuple[int | None, str]:
    """
    เพิ่มผู้ใช้จากรูปภาพที่อัปโหลด (base64 encoded JPEG/PNG จาก browser)
    • ใช้ PIL เพื่อรองรับทุกฟอร์แมต (PNG, JPEG, WEBP, RGBA, EXIF)
    • สร้าง face encoding (128-D vector)
    • บันทึก encoding + รูป ลง database/disk
    คืนค่า (user_id, message)
    """
    ensure_dirs()

    if not FR_AVAILABLE:
        return None, "face_recognition ไม่ได้ติดตั้ง — ไม่สามารถสร้าง face encoding ได้"

    try:
        from PIL import Image

        # Decode base64 → RGB numpy array (PIL รองรับ RGBA, EXIF, grayscale ทุกฟอร์แมต)
        img_bytes = base64.b64decode(image_base64.strip())
        pil_img   = Image.open(BytesIO(img_bytes)).convert('RGB')
        rgb       = np.array(pil_img, dtype=np.uint8)   # shape (H, W, 3) RGB
        frame_bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR) # BGR สำหรับบันทึกไฟล์

        # Detect face and create encoding
        locs = fr.face_locations(rgb, model="hog")
        if not locs:
            return None, "ไม่พบใบหน้าในรูปภาพ — กรุณาใช้รูปที่เห็นใบหน้าตรงและชัดเจน"

        encs = fr.face_encodings(rgb, locs)
        if not encs:
            return None, "ไม่สามารถสร้าง face encoding ได้"

        encoding = encs[0]  # ใช้ใบหน้าแรกที่พบ

        # บันทึกรูปลงดิสก์ (JPEG)
        ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
        img_path  = os.path.join(FACES_DIR, f"{safe_name}_{ts}.jpg")
        cv2.imwrite(img_path, frame_bgr)

        # บันทึก encoding + path ลง database
        enc_bytes = pickle.dumps(encoding)
        uid = db.add_user(name, enc_bytes, img_path)
        return uid, "success"

    except Exception as e:
        return None, f"เกิดข้อผิดพลาด: {str(e)}"


def update_user_face_from_image(user_id: int, name: str | None,
                                image_base64: str | None) -> tuple[bool, str]:
    """
    อัปเดตข้อมูลผู้ใช้:
    - name: ถ้าส่งมา → อัปเดตชื่อ
    - image_base64: ถ้าส่งมา → decode, detect face, สร้าง encoding ใหม่, บันทึกรูปใหม่
    คืนค่า (success: bool, message: str)
    """
    ensure_dirs()

    try:
        if image_base64:
            if not FR_AVAILABLE:
                return False, "face_recognition ไม่ได้ติดตั้ง"

            from PIL import Image

            img_bytes = base64.b64decode(image_base64.strip())
            pil_img   = Image.open(BytesIO(img_bytes)).convert('RGB')
            rgb       = np.array(pil_img, dtype=np.uint8)
            frame_bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

            locs = fr.face_locations(rgb, model="hog")
            if not locs:
                return False, "ไม่พบใบหน้าในรูปภาพ — กรุณาใช้รูปที่เห็นใบหน้าตรงและชัดเจน"

            encs = fr.face_encodings(rgb, locs)
            if not encs:
                return False, "ไม่สามารถสร้าง face encoding ได้"

            encoding  = encs[0]
            enc_bytes = pickle.dumps(encoding)

            ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = "".join(c if c.isalnum() or c in "._-" else "_"
                                for c in (name or f"user{user_id}"))
            img_path  = os.path.join(FACES_DIR, f"{safe_name}_{ts}.jpg")
            cv2.imwrite(img_path, frame_bgr)

            db.update_user(user_id, name, enc_bytes, img_path, replace_image=True)
        else:
            # อัปเดตชื่ออย่างเดียว
            db.update_user(user_id, name)

        return True, "success"

    except Exception as e:
        return False, f"เกิดข้อผิดพลาด: {str(e)}"
