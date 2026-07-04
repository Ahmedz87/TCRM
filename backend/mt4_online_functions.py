def get_online_users():
    """Fetch currently online MT4 users (login + IP)."""
    man   = get_manager()
    total = c_int(0)
    ptr   = vcall(man, V_ONLINE_GET, c_void_p, [POINTER(c_int)], byref(total))
    if not ptr or total.value <= 0:
        return []
    stride = sizeof(OnlineRecord)
    result = []
    for i in range(total.value):
        rec   = OnlineRecord.from_address(ptr + i * stride)
        ip_int = rec.ip
        ip_str = f"{ip_int & 0xFF}.{(ip_int>>8)&0xFF}.{(ip_int>>16)&0xFF}.{(ip_int>>24)&0xFF}"
        result.append({
            "login": rec.login,
            "ip":    ip_str,
            "group": rec.group.decode("utf-8", errors="ignore").strip(),
        })
    mem_free(ptr)
    log.info("OnlineGet: %d users online", len(result))
    return result


def save_online_identifiers(online: list):
    """Upsert current online IPs into account_identifiers."""
    from sqlalchemy import text
    from datetime import datetime, timezone
    if not online:
        return
    db  = get_db()
    now = datetime.now(timezone.utc)
    try:
        for o in online:
            if not o["ip"] or o["ip"].startswith("0."):
                continue
            db.execute(text("""
                INSERT INTO account_identifiers
                    (login, identifier_type, identifier_value, first_seen, last_seen, seen_count)
                VALUES (:login, 'ip', :ip, :now, :now, 1)
                ON CONFLICT (login, identifier_type, identifier_value)
                DO UPDATE SET
                    last_seen  = EXCLUDED.last_seen,
                    seen_count = account_identifiers.seen_count + 1
            """), {"login": o["login"], "ip": o["ip"], "now": now})
        db.commit()
        log.info("Online identifiers: %d IPs upserted", len(online))
    except Exception as e:
        db.rollback()
        log.error("save_online_identifiers: %s", e)
    finally:
        db.close()
