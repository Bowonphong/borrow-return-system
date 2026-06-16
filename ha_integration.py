"""
ha_integration.py — Home Assistant integration
รองรับทั้ง REST API และ MQTT
"""

import json
from datetime import datetime

import config as cfg


# ─────────────────────────────────────────────────────────────
#  REST API
# ─────────────────────────────────────────────────────────────
def _ha_headers() -> dict:
    return {
        "Authorization": f"Bearer {cfg.HA_TOKEN}",
        "Content-Type": "application/json",
    }


def _post_ha_state(entity_id: str, state: str, attributes: dict | None = None):
    if not cfg.HA_ENABLED:
        return
    try:
        import requests
        url = f"{cfg.HA_URL}/api/states/sensor.{entity_id}"
        payload = {
            "state": state,
            "attributes": {
                "friendly_name": entity_id.replace("_", " ").title(),
                "updated_at": datetime.now().isoformat(),
                **(attributes or {}),
            },
        }
        requests.post(url, headers=_ha_headers(), json=payload, timeout=5)
    except Exception as e:
        print(f"[HA REST] {e}")


def _fire_ha_event(event_name: str, data: dict):
    if not cfg.HA_ENABLED:
        return
    try:
        import requests
        url = f"{cfg.HA_URL}/api/events/{event_name}"
        requests.post(url, headers=_ha_headers(), json=data, timeout=5)
    except Exception as e:
        print(f"[HA Event] {e}")


# ─────────────────────────────────────────────────────────────
#  MQTT
# ─────────────────────────────────────────────────────────────
def _mqtt_publish(topic_suffix: str, payload: dict):
    if not cfg.MQTT_ENABLED:
        return
    try:
        import paho.mqtt.publish as publish
        topic = f"{cfg.MQTT_TOPIC_PREFIX}/{topic_suffix}"
        auth = (
            {"username": cfg.MQTT_USER, "password": cfg.MQTT_PASSWORD}
            if cfg.MQTT_USER
            else None
        )
        publish.single(
            topic,
            payload=json.dumps(payload, ensure_ascii=False),
            hostname=cfg.MQTT_HOST,
            port=cfg.MQTT_PORT,
            auth=auth,
        )
    except Exception as e:
        print(f"[MQTT] {e}")


# ─────────────────────────────────────────────────────────────
#  Public notify functions
# ─────────────────────────────────────────────────────────────
def notify_borrow(user_name: str, item_name: str, total_borrowed: int):
    ts = datetime.now().isoformat()
    data = {
        "action": "borrow",
        "user_name": user_name,
        "item_name": item_name,
        "total_borrowed": total_borrowed,
        "timestamp": ts,
    }
    # REST: fire event + update sensors
    _fire_ha_event("borrow_system_borrow", data)
    _post_ha_state("borrow_last_action", f"{user_name} ยืม {item_name}", {"timestamp": ts})
    _post_ha_state("borrow_total_borrowed", str(total_borrowed))
    # MQTT
    _mqtt_publish("borrow", data)
    _mqtt_publish("status/total_borrowed", {"value": total_borrowed})


def notify_return(user_name: str, item_name: str, total_borrowed: int):
    ts = datetime.now().isoformat()
    data = {
        "action": "return",
        "user_name": user_name,
        "item_name": item_name,
        "total_borrowed": total_borrowed,
        "timestamp": ts,
    }
    _fire_ha_event("borrow_system_return", data)
    _post_ha_state("borrow_last_action", f"{user_name} คืน {item_name}", {"timestamp": ts})
    _post_ha_state("borrow_total_borrowed", str(total_borrowed))
    _mqtt_publish("return", data)
    _mqtt_publish("status/total_borrowed", {"value": total_borrowed})


def push_full_status(total_users: int, total_items: int, total_borrowed: int):
    """เรียกตอนเริ่มระบบ เพื่ออัปเดต HA ด้วยสถานะล่าสุด"""
    _post_ha_state("borrow_total_users", str(total_users))
    _post_ha_state("borrow_total_items", str(total_items))
    _post_ha_state("borrow_total_borrowed", str(total_borrowed))
    _mqtt_publish("status/startup", {
        "total_users": total_users,
        "total_items": total_items,
        "total_borrowed": total_borrowed,
    })
