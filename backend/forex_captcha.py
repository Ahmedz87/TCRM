"""
forex_captcha.py — a fun, self-hosted, forex-themed bot check.

Renders a small candlestick image ON THIS SERVER (no external service / keys). One candle
matches the asked direction (green ▲ up / red ▼ down), the rest are the opposite — the user
taps it. The answer is stored server-side (single-use, 5-min expiry) and verified in send-otp,
so it's a real server-checked challenge — a good deterrent (not as bullet-proof as Turnstile
against scripted bots; layer Turnstile behind it if you ever want max protection).
"""
import base64
import random
import datetime
import numpy as np
import cv2
from sqlalchemy import text

N = 4          # number of candles (slots)
W, H = 360, 150


def ensure(db):
    db.execute(text("""CREATE TABLE IF NOT EXISTS captcha_challenges (
        id SERIAL PRIMARY KEY, answer INT, expires_at TIMESTAMP, used BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT NOW())"""))
    db.commit()


def generate(db):
    ensure(db)
    ask_up = random.random() < 0.5
    correct = random.randrange(N)
    img = np.full((H, W, 3), 26, np.uint8)                       # dark bg
    cv2.line(img, (0, H // 2), (W, H // 2), (45, 50, 60), 1)     # faint baseline
    slot_w = W // N
    for i in range(N):
        up = ask_up if i == correct else (not ask_up)
        cx = i * slot_w + slot_w // 2
        bodyh = random.randint(34, 72)
        wick = random.randint(12, 26)
        mid = H // 2 + random.randint(-14, 14)
        top, bot = mid - bodyh // 2, mid + bodyh // 2
        color = (90, 220, 90) if up else (70, 70, 235)          # BGR: green / red
        cv2.line(img, (cx, top - wick), (cx, bot + wick), color, 2)
        cv2.rectangle(img, (cx - 11, top), (cx + 11, bot), color, -1)
    ok, buf = cv2.imencode(".png", img)
    b64 = base64.b64encode(buf.tobytes()).decode()
    cid = db.execute(text("""INSERT INTO captcha_challenges (answer, expires_at)
                             VALUES (:a, NOW() + INTERVAL '5 minutes') RETURNING id"""),
                     {"a": correct}).scalar()
    db.commit()
    prompt = "Tap the GREEN candle going UP ▲" if ask_up else "Tap the RED candle going DOWN ▼"
    return {"id": cid, "image": "data:image/png;base64," + b64, "prompt": prompt, "slots": N}


def verify(db, cid, slot):
    """One attempt per challenge (marks it used regardless), single-use, 5-min expiry."""
    ensure(db)
    try:
        cid = int(cid); slot = int(slot)
    except (TypeError, ValueError):
        return False
    row = db.execute(text("SELECT answer, expires_at, used FROM captcha_challenges WHERE id=:i"),
                     {"i": cid}).fetchone()
    if not row:
        return False
    ans, exp, used = row
    if used or (exp and datetime.datetime.utcnow() > exp):
        return False
    db.execute(text("UPDATE captcha_challenges SET used=TRUE WHERE id=:i"), {"i": cid})
    db.commit()
    return slot == int(ans)
