def sync_login_identifiers(days: int = 1):
    """Parse journal login entries for IP + CID and upsert to account_identifiers.
    Runs in the 5-min cycle to keep network identifiers fresh.
    """
    import re
    from ctypes import string_at
    from sqlalchemy import text
    man = get_manager()
    SERVERLOG_SIZE = 796
    OFFSET_IP  = 28
    OFFSET_MSG = 284
    RE_LOGIN = re.compile(r"'(\d+)':\s*login")
    RE_CID   = re.compile(r"\bcid:\s*([0-9a-fA-F]{16,})")
    from_time = int(time.time()) - days * 86400
    to_time   = int(time.time())
    total = c_int(0)
    ptr = vcall(man, 96, c_void_p,
                [c_int, c_int, c_int, c_char_p, POINTER(c_int)],
                1, from_time, to_time, b"", byref(total))
    if not ptr or total.value <= 0:
        return
    login_ips  = {}
    login_cids = {}
    for i in range(total.value):
        off_ip  = ptr + i * SERVERLOG_SIZE + OFFSET_IP
        off_msg = ptr + i * SERVERLOG_SIZE + OFFSET_MSG
        ip  = string_at(off_ip, 256).split(b"\x00")[0].decode("utf-8", errors="ignore").strip()
        msg = string_at(off_msg, 512).split(b"\x00")[0].decode("utf-8", errors="ignore")
        m = RE_LOGIN.search(msg)
        if not m:
            continue
        login = int(m.group(1))
        if login <= 0:
            continue
        if ip:
            login_ips.setdefault(login, set()).add(ip)
        mc = RE_CID.search(msg)
        if mc:
            login_cids.setdefault(login, set()).add(mc.group(1).lower())
    mem_free(ptr)

    db = get_db()
    now = datetime.now(timezone.utc)
    try:
        for login, ips in login_ips.items():
            for ip in ips:
                if not ip or ip.startswith("0."):
                    continue
                db.execute(text("""
                    INSERT INTO account_identifiers (login, identifier_type, identifier_value, first_seen, last_seen, seen_count)
                    VALUES (:login, 'ip', :v, :now, :now, 1)
                    ON CONFLICT (login, identifier_type, identifier_value)
                    DO UPDATE SET last_seen=:now, seen_count=account_identifiers.seen_count+1
                """), {"login": login, "v": ip, "now": now})
        for login, cids in login_cids.items():
            for cid in cids:
                db.execute(text("""
                    INSERT INTO account_identifiers (login, identifier_type, identifier_value, first_seen, last_seen, seen_count)
                    VALUES (:login, 'cid', :v, :now, :now, 1)
                    ON CONFLICT (login, identifier_type, identifier_value)
                    DO UPDATE SET last_seen=:now, seen_count=account_identifiers.seen_count+1
                """), {"login": login, "v": cid, "now": now})
        db.commit()
        log.info("MT4 identifiers: %d logins with IP, %d with CID", len(login_ips), len(login_cids))
    except Exception as e:
        db.rollback()
        log.error("sync_login_identifiers: %s", e)
    finally:
        db.close()
