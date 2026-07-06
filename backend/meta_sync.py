"""
Meta Ads Leads Sync — pulls leads from Meta Lead Ads (Facebook/Instagram/Messenger/Audience Network)
Captures: source platform, publisher app/site, ALL custom qualifying questions
Run:       python meta_sync.py
Loop:      python meta_sync.py --loop   (every 5 min)
"""
import urllib.request, json, ssl, sys, time
from datetime import datetime

sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text
import meta_config

# ── CONFIG ───────────────────────────────────────────────────────────────────
PAGE_ID = meta_config.META_PAGE_ID
TOKEN   = meta_config.META_ACCESS_TOKEN

ctx = ssl.create_default_context()   # verify TLS: graph.facebook.com has a valid public cert
GRAPH = "https://graph.facebook.com/v21.0"

# Standard field names we map to dedicated columns
NAME_KEYS    = ("full_name", "first_name", "name", "الاسم", "اسم")
PHONE_KEYS   = ("phone", "phone_number", "هاتف", "جوال", "رقم")
EMAIL_KEYS   = ("email", "بريد", "ايميل")
COUNTRY_KEYS = ("country", "دولة", "بلد")

def fb_get(path):
    url = f"{GRAPH}{path}"
    sep = "&" if "?" in path else "?"
    url += f"{sep}access_token={TOKEN}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla"})
    try:
        r = urllib.request.urlopen(req, context=ctx, timeout=30)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()[:300]}
    except Exception as e:
        return {"error": str(e)}

def get_page_token():
    accounts = fb_get("/me/accounts?fields=id,access_token")
    if "data" in accounts:
        for acc in accounts["data"]:
            if acc.get("id") == PAGE_ID:
                return acc["access_token"]
    return TOKEN

def clean(val, maxlen):
    if not val:
        return ""
    return str(val).strip()[:maxlen]

def is_standard(field_name):
    fn = field_name.lower()
    for keys in (NAME_KEYS, PHONE_KEYS, EMAIL_KEYS, COUNTRY_KEYS):
        if any(k in fn for k in keys):
            return True
    return False

def extract_standard(field_data, keys):
    for fd in field_data:
        fname = fd.get("name", "").lower()
        if any(k in fname for k in keys):
            vals = fd.get("values", [])
            return vals[0] if vals else ""
    return ""

def extract_custom_questions(field_data):
    """All non-standard fields = custom qualifying questions."""
    questions = []
    for fd in field_data:
        name = fd.get("name", "")
        if is_standard(name):
            continue
        vals = fd.get("values", [])
        answer = ", ".join(str(v) for v in vals) if vals else ""
        questions.append({"q": name, "a": answer})
    return questions

def map_platform(platform_raw):
    p = (platform_raw or "").lower()
    if "instagram" in p or p == "ig":
        return "instagram"
    if "messenger" in p:
        return "messenger"
    if "audience_network" in p or p == "an":
        return "audience_network"
    if "facebook" in p or p == "fb":
        return "facebook"
    return platform_raw or "facebook"

def get_all_forms(page_token):
    forms, seen = [], set()
    url = f"{GRAPH}/{PAGE_ID}/leadgen_forms?fields=id,name,leads_count,status&limit=50&access_token={page_token}"
    while url:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla"})
        try:
            data = json.loads(urllib.request.urlopen(req, context=ctx, timeout=30).read())
        except Exception as e:
            print(f"  Error listing forms: {e}")
            break
        for f in data.get("data", []):
            if f["id"] not in seen:
                seen.add(f["id"])
                forms.append(f)
        url = data.get("paging", {}).get("next")
    return forms

def sync_form_leads(form_id, form_name, page_token, db):
    inserted = skipped = errors = 0
    fields = "created_time,field_data,platform,ad_name,adset_name,campaign_name"
    url = f"{GRAPH}/{form_id}/leads?fields={fields}&limit=100&access_token={page_token}"
    while url:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla"})
        try:
            data = json.loads(urllib.request.urlopen(req, context=ctx, timeout=30).read())
        except Exception as e:
            print(f"    Error: {e}")
            break

        for lead in data.get("data", []):
            meta_lead_id  = lead.get("id")
            created       = lead.get("created_time", "")
            fd            = lead.get("field_data", [])
            platform_raw  = lead.get("platform", "")
            ad_name       = lead.get("ad_name", "")
            adset_name    = lead.get("adset_name", "")
            campaign_name = lead.get("campaign_name", "") or form_name

            source = map_platform(platform_raw)
            full_name = clean(extract_standard(fd, NAME_KEYS), 200)
            phone     = clean(extract_standard(fd, PHONE_KEYS), 50)
            email     = clean(extract_standard(fd, EMAIL_KEYS), 200)
            country   = clean(extract_standard(fd, COUNTRY_KEYS), 100)
            custom_qs = extract_custom_questions(fd)

            try:
                existing = db.execute(text(
                    "SELECT id FROM leads WHERE meta_lead_id = :mid"
                ), {"mid": meta_lead_id}).fetchone()
                if existing:
                    skipped += 1
                    continue

                try:
                    created_dt = datetime.strptime(created, "%Y-%m-%dT%H:%M:%S%z")
                except:
                    created_dt = datetime.utcnow()

                db.execute(text("""
                    INSERT INTO leads (
                        full_name, phone, email, country, language,
                        source, platform, campaign_name, ad_name, adset_name,
                        meta_platform, custom_questions, status,
                        meta_lead_id, fb_form_id, created_at, updated_at
                    ) VALUES (
                        :name, :phone, :email, :country, 'ar',
                        :source, :source, :campaign, :ad_name, :adset_name,
                        :source, CAST(:custom AS JSONB), 'new',
                        :mid, :form_id, :created, NOW()
                    )
                """), {
                    "name": full_name, "phone": phone, "email": email,
                    "country": country, "source": source,
                    "campaign": clean(campaign_name, 200),
                    "ad_name": clean(ad_name, 200), "adset_name": clean(adset_name, 200),
                    "custom": json.dumps(custom_qs, ensure_ascii=False),
                    "mid": meta_lead_id, "form_id": form_id, "created": created_dt
                })
                db.commit()
                inserted += 1
            except Exception as e:
                db.rollback()
                errors += 1
                continue

        url = data.get("paging", {}).get("next")

    return inserted, skipped, errors

def run_sync():
    print("=" * 50)
    print("Meta Ads Leads Sync")
    print("=" * 50)
    page_token = get_page_token()
    db = SessionLocal()
    db.rollback()
    try:
        forms = get_all_forms(page_token)
        print(f"Found {len(forms)} forms\n")
        total_new = 0
        for f in forms:
            fid, fname, count = f["id"], f.get("name", ""), f.get("leads_count", 0)
            if count == 0:
                continue
            print(f"Syncing '{fname}' ({count} leads)...")
            ins, skp, err = sync_form_leads(fid, fname, page_token, db)
            print(f"   +{ins} new, {skp} existed, {err} errors")
            total_new += ins
        print(f"\nDone! {total_new} new leads imported.")

        print("\n=== Source breakdown ===")
        rows = db.execute(text("""
            SELECT meta_platform, COUNT(*) FROM leads
            WHERE meta_platform IS NOT NULL
            GROUP BY meta_platform ORDER BY COUNT(*) DESC
        """)).fetchall()
        for r in rows:
            print(f"   {r[0]}: {r[1]}")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    if "--loop" in sys.argv:
        while True:
            run_sync()
            print("\nSleeping 5 minutes...\n")
            time.sleep(300)
    else:
        run_sync()
