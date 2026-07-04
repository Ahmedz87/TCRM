from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
import models


def get_score_settings(db: Session):
    settings = db.query(models.ScoreSettings).first()
    if not settings:
        settings = models.ScoreSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def calculate_network_score(client: dict, all_clients: list) -> dict:
    login = client.get("login")
    ip    = client.get("lastIP") or client.get("ip", "")
    cid   = client.get("clientID") or client.get("cid", "")
    city  = client.get("city", "").lower()
    ib    = str(client.get("agent", ""))

    connections = []
    points = 0

    for other in all_clients:
        if other.get("login") == login:
            continue

        other_ip   = other.get("lastIP") or other.get("ip", "")
        other_cid  = other.get("clientID") or other.get("cid", "")
        other_city = other.get("city", "").lower()
        other_ib   = str(other.get("agent", ""))

        reasons = []

        if ip and other_ip and ip == other_ip:
            reasons.append("IP")
            points += 3
        if cid and other_cid and cid == other_cid:
            reasons.append("CID")
            points += 3
        if city and other_city and city == other_city and city not in ["", "unknown"]:
            reasons.append("City")
            points += 1
        if ib and other_ib and ib == other_ib and ib not in ["0", ""]:
            reasons.append("IB")
            points += 1

        if reasons:
            connections.append({
                "login":   other.get("login"),
                "name":    other.get("name", ""),
                "reasons": reasons,
            })

    score = min(10, points)

    if score <= 2:
        color = "green"
    elif score <= 4:
        color = "yellow"
    elif score <= 6:
        color = "orange"
    else:
        color = "red"

    return {
        "score":       score,
        "color":       color,
        "connections": connections[:10],
    }


def calculate_call_score(client: dict, last_action: dict, settings) -> int:
    score = 0
    now   = datetime.now(timezone.utc)

    balance      = float(client.get("balance", 0) or 0)
    equity       = float(client.get("equity", 0) or 0)
    margin_level = float(client.get("marginLevel", client.get("margin_level", 0)) or 0)
    kyc          = client.get("kycStatus", client.get("kyc", "pending"))

    # Margin call active
    if 0 < margin_level < 20:
        score += settings.margin_call_score

    # Margin below threshold
    if 0 < margin_level < settings.margin_threshold:
        score += settings.margin_below_threshold_score

    # Low equity
    if balance > 0 and equity < (balance * settings.low_equity_threshold / 100):
        score += settings.low_equity_score

    # High balance
    if balance >= settings.high_balance_threshold:
        score += settings.high_balance_inactive_score

    # KYC pending
    if kyc == "pending":
        score += settings.kyc_pending_score

    # Never deposited
    if balance == 0 and equity == 0:
        score += settings.never_deposited_score

    if last_action:
        action     = last_action.get("action", "")
        created_at = last_action.get("created_at")
        call_later = last_action.get("call_later_at")

        # Connected and done cooldown
        if action == "connected_done" and created_at:
            if isinstance(created_at, str):
                try:
                    created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                except Exception:
                    created_at = None
            if created_at and (now - created_at).days < 14:
                score -= 100

        # Call later boost
        if action == "call_later" and call_later:
            if isinstance(call_later, str):
                try:
                    call_later = datetime.fromisoformat(call_later.replace("Z", "+00:00"))
                except Exception:
                    call_later = None
            if call_later and now >= call_later:
                score += 100

        # No answer escalating
        if action == "no_answer" and created_at:
            if isinstance(created_at, str):
                try:
                    created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                except Exception:
                    created_at = None
            if created_at:
                hours = (now - created_at).total_seconds() / 3600
                if hours >= 96:
                    score += 40
                elif hours >= 48:
                    score += 30
                elif hours >= 24:
                    score += 20
                elif hours >= 2:
                    score += 10

    return max(0, score)
