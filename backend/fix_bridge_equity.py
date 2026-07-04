with open(r'C:\broker-crm\backend\bridge.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('def update_live_data')
end = content.find('\ndef ', idx + 10)
old_func = content[idx:end]

new_func = '''def update_live_data(manager, db):
    """Every 30s: update equity and margin_level using UserAccountGetByGroup (real equity).
    Also syncs email and MQID from UserGetByGroup for network detection."""
    try:
        # Use UserAccountGetByGroup for REAL equity/margin (includes floating P&L)
        accounts = manager.UserAccountGetByGroup("*") or []
        if not accounts:
            log.warning("UserAccountGetByGroup returned empty")
            return
        updated = 0
        for a in accounts:
            try:
                login        = getattr(a, 'Login', 0)
                balance      = round(float(getattr(a, 'Balance', 0) or 0), 2)
                equity       = round(float(getattr(a, 'Equity', 0) or 0), 2)
                margin       = round(float(getattr(a, 'Margin', 0) or 0), 2)
                margin_level = round(float(getattr(a, 'MarginLevel', 0) or 0), 2)
                free_margin  = round(float(getattr(a, 'MarginFree', 0) or 0), 2)
                # equity=0 with no positions means no open trades — use balance
                if equity == 0 and margin == 0 and balance > 0:
                    equity = balance
                if not login:
                    continue
                db.execute(
                    text("UPDATE clients SET equity=:eq, margin_level=:ml, balance=:bal WHERE login=:l"),
                    {"eq": equity, "ml": margin_level, "bal": balance, "l": login}
                )
                db.execute(
                    text("UPDATE trading_accounts SET equity=:eq, margin_level=:ml, free_margin=:fm, balance=:bal WHERE login=:l"),
                    {"eq": equity, "ml": margin_level, "fm": free_margin, "bal": balance, "l": login}
                )
                updated += 1
            except Exception:
                continue
        db.commit()
        log.info("Live data updated: %d accounts (equity+margin+balance)", updated)

        # Also save email and MQID from UserGetByGroup for network detection
        try:
            all_users = manager.UserGetByGroup("*") or []
            email_count = 0
            mqid_count  = 0
            for u in all_users:
                login = getattr(u, 'Login', 0)
                email = getattr(u, 'Email', '') or ''
                mqid  = getattr(u, 'MQID', 0) or getattr(u, 'MQId', 0) or 0
                if not login:
                    continue
                if email and '@' in email:
                    existing = db.query(models.AccountIdentifier).filter(
                        models.AccountIdentifier.login == login,
                        models.AccountIdentifier.identifier_type == 'email',
                        models.AccountIdentifier.identifier_value == email,
                    ).first()
                    if not existing:
                        db.add(models.AccountIdentifier(login=login, identifier_type='email', identifier_value=email))
                        email_count += 1
                    # Save email to clients table
                    db.execute(text("UPDATE clients SET email=:e WHERE login=:l AND (email IS NULL OR email='')"),
                               {"e": email, "l": login})
                if mqid and mqid != 0:
                    mqid_str = str(mqid)
                    existing = db.query(models.AccountIdentifier).filter(
                        models.AccountIdentifier.login == login,
                        models.AccountIdentifier.identifier_type == 'mqid',
                        models.AccountIdentifier.identifier_value == mqid_str,
                    ).first()
                    if not existing:
                        db.add(models.AccountIdentifier(login=login, identifier_type='mqid', identifier_value=mqid_str))
                        mqid_count += 1
            db.commit()
            log.info("Email/MQID sync: %d new emails, %d new MQIDs", email_count, mqid_count)
        except Exception as e:
            db.rollback()
            log.error("Email/MQID sync error: %s", e)

    except Exception as e:
        db.rollback()
        log.error("update_live_data error: %s", e)
'''

content = content[:idx] + new_func + content[end:]
print("Function replaced, new length:", len(new_func))
print("UserAccountGetByGroup in bridge:", "UserAccountGetByGroup" in content)
print("email sync in bridge:", "email_count" in content)

with open(r'C:\broker-crm\backend\bridge.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("bridge.py saved!")
