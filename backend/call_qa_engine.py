"""
call_qa_engine.py — automatic per-call QA reports for the sales floor.

Pipeline: Yeastar PBX recording -> local Whisper transcription (Arabic) ->
Claude Haiku scoring -> `call_qa` table. Each call gets a SHORT report card:
strengths / weaknesses / one recommendation / score 0-10 / priority
(critical | urgent | medium | normal) so managers know which calls to review.

RUN UNDER THE DEDICATED VENV (has faster-whisper + anthropic + psycopg2):
    C:\\broker-crm\\callqa\\venv\\Scripts\\python.exe call_qa_engine.py [--hours 24] [--limit 30] [--loop]

Transcription is CPU-heavy (~1x realtime). cpu_threads=2 + per-cycle limit keep
the live box responsive; move this to S4 if daily volume outgrows S1.
Idempotent: recordings are keyed by PBX recording id (ON CONFLICT DO NOTHING).
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import db_config
import yeastar_service as ys

MODEL_DIR = r"C:\broker-crm\callqa\model"
WAV_DIR = r"C:\broker-crm\callqa\wav"
KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_key.txt")
CLAUDE_MODEL = "claude-haiku-4-5"
MIN_DURATION = 25          # skip no-answer / hangup stubs
MAX_DURATION = 1800
SHARD = None               # set via --shard k/m: process only recordings where id % m == k

_whisper = None


def _log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# ---------------------------------------------------------------- PBX helpers

def _pbx_api(path_qs, tok):
    sep = "&" if "?" in path_qs else "?"
    url = f"https://{ys.PBX_HOST}{path_qs}{sep}access_token={tok}"
    req = urllib.request.Request(url, headers={"User-Agent": "OpenAPI"})
    with urllib.request.urlopen(req, context=ys._CTX, timeout=30) as r:
        return json.loads(r.read())


def fetch_recent_recordings(hours):
    """Newest-first recordings from the last `hours` hours."""
    tok = ys._ensure_token()
    if not tok:
        raise RuntimeError("could not obtain PBX token")
    out, page = [], 1
    cutoff = time.time() - hours * 3600
    while page <= 250:
        res = _pbx_api(f"/openapi/v1.0/recording/list?page={page}&page_size=100"
                       f"&sort_by=time&order_by=desc", tok)
        rows = res.get("data") or []
        if not rows:
            break
        stop = False
        for r in rows:
            try:
                ts = datetime.strptime(r["time"], "%m/%d/%Y %H:%M:%S").timestamp()
            except Exception:
                continue
            if ts < cutoff:
                stop = True
                break
            r["_ts"] = ts
            out.append(r)
        if stop:
            break
        page += 1
    return out, tok


def download_recording(rec, tok=None):
    """Download one recording. TOKEN-SAFE (#287/#289): a scoring cycle takes far longer than a
    PBX token lives (transcription ≈ minutes per call), so the cycle-start token routinely died
    mid-batch — every later download failed with errcode 10004 TOKEN EXPIRED (950 failures in the
    gap log). Always re-resolve the token just before use, and on a PBX 'expired' verdict force a
    re-login and retry once."""
    dl = None
    for attempt in (1, 2):
        tok = ys._ensure_token() or tok
        dl = _pbx_api(f"/openapi/v1.0/recording/download?id={rec['id']}", tok)
        if str(dl.get("errcode")) == "10004" or "TOKEN" in str(dl.get("errmsg", "")).upper():
            ys._token_exp = 0          # our clock disagreed with the PBX — force full refresh
            if attempt == 1:
                continue
        break
    url = dl.get("download_resource_url")
    if not url:
        raise RuntimeError(f"no download url for recording {rec['id']}: {dl}")
    os.makedirs(WAV_DIR, exist_ok=True)
    out = os.path.join(WAV_DIR, f"{rec['id']}.wav")
    full = f"https://{ys.PBX_HOST}{url}?access_token={tok}"
    req = urllib.request.Request(full, headers={"User-Agent": "OpenAPI"})
    with urllib.request.urlopen(req, context=ys._CTX, timeout=180) as r, open(out, "wb") as f:
        f.write(r.read())
    return out


# ------------------------------------------------------------- transcription

def transcribe(wav_path):
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        _whisper = WhisperModel(MODEL_DIR, device="cpu", compute_type="int8", cpu_threads=2)
    segments, info = _whisper.transcribe(wav_path, vad_filter=False, beam_size=5)
    segs = [{"s": round(sg.start, 1), "e": round(sg.end, 1), "t": sg.text.strip()}
            for sg in segments]
    text = "\n".join(f"[{sg['s']:.0f}s] {sg['t']}" for sg in segs)
    return text, segs, info.language


# ------------------------------------------------------------------ scoring

SCORING_SYSTEM = """أنت مدرب مبيعات محترف وخبير جودة مكالمات في شركة وساطة فوركس (TNFX). ستستلم تفريغاً آلياً لمكالمة مبيعات/متابعة بالعربية (لهجة سورية/عراقية). المكالمة عادة بين موظف مبيعات وعميل/ليد. مهمتك: تقرير يعلّم الموظف فعلياً كيف يصير أفضل، وليس مجرد ملاحظات عامة.

قواعد التعامل مع التفريغ الآلي — اقرأها قبل أي حكم (سبق أن ظلمنا موظفين بسبب تجاهلها):
- التفريغ ناتج تعرّف آلي على كلام هاتفي بلهجات سورية/عراقية، وفيه أخطاء منهجية: كلمات مسموعة غلط، جمل مبتورة، وأسماء الأعلام تتشوّه دائماً تقريباً.
- أسماء الأشخاص: أي كلمة غريبة أو مضحكة أو حتى مسيئة واقعة في موضع الاسم (بعد "أستاذ/سيد/مرحبا/أخ") اعتبرها تشويهَ تفريغ لاسم حقيقي — ليست شتيمة ولا خطأ من الموظف. لا تتهم موظفاً بإهانة عميل استناداً إلى كلمة واحدة من التفريغ أبداً؛ الإهانة الحقيقية يؤكدها السياق (غضب العميل واعتراضه، تكرار الإساءة، مجرى عدائي كامل). وهذا يشمل كل حقول التقرير — لا تذكر الكلمة المشوّهة ولا تقتبسها في summary أو analysis أو أي حقل آخر كأنها "تحية غير لائقة" أو خطأ؛ تعامل معها ببساطة كأن الموظف نادى العميل باسمه بشكل طبيعي.
- اسم الشركة TNFX يُفرَّغ غلط كثيراً (2FX، تو اف اكس، TFX، تي ان اف...). لا تتهم الموظف بذكر اسم شركة خاطئ استناداً إلى التفريغ.
- لا تقتبس عبارة مشوّهة كدليل على خطأ الموظف، ولا تبنِ نقطة ضعف أو مخالفة على كلمة يُحتمل أنها خطأ تفريغ. المخالفة تحتاج معنىً واضحاً من جملة كاملة وسياق متّسق قبلها وبعدها.
- قيّم السلوك ومجرى الحوار، لا الصياغة الحرفية للكلمات.

نوع المكالمة — أولى أم متابعة (قيّم كل نوع بمعاييره):
- سيصلك في الرسالة "سجل المكالمات السابقة" مع هذا الرقم إن وُجد. السجل يشمل المسجَّل عندنا فقط؛ إذا كان فارغاً لكن الحديث نفسه يدل على معرفة سابقة (يناديه باسمه مباشرة، يكمل موضوعاً سابقاً، "متل ما حكينا") فاعتبرها متابعة.
- مكالمة المتابعة لا تُقيَّم بمعايير المكالمة الأولى: لا تنتقد الموظف على عدم تعريف نفسه والشركة من جديد، ولا على عدم طرح أسئلة تعارف واكتشاف أساسية سبق جمعها. قيّم بدلها: هل ربط بالمكالمة السابقة وذكّر بما اتُّفق عليه؟ هل نفّذ ما وَعَد به سابقاً؟ هل أضاف قيمة جديدة وقدّم خطوة ملموسة تالية؟
- المكالمة الأولى فقط هي التي تُطبَّق عليها معايير الافتتاحية الكاملة (تعريف بالاسم والشركة، سبب الاتصال، إذن بالوقت).
- الـ coaching يجب أن يطابق نوع المكالمة: افتتاحية المتابعة الصحيحة = ترحيب حار بالاسم + ربط فوري بآخر تواصل + سبب مكالمة اليوم — وليس إعادة تعريف بالشركة.

المكالمات القصيرة أو الفاشلة تقنياً:
- مكالمة أقصر من ~40 ثانية أو بلا محادثة فعلية (ما رد، انقطعت، مجاملة سريعة): لا تعاملها كمكالمة مبيعات فاشلة ولا تكتب "المكالمة فشلت تجارياً" ولا تعطها critical بسبب "غياب هدف تجاري" — outcome المناسب (غالباً no_conversation) و priority=normal، والـ coaching عن كيف يستغل المحاولة الجاية. (المخالفة الصريحة الواضحة تبقى critical حتى في مكالمة قصيرة.)

سياق مهم جداً عن النظام (لا تخالفه):
- موظف المبيعات يشاهد أمامه في الـ CRM كل بيانات العميل/الليد: الاسم، الهاتف، البلد، الإيميل. لذلك لا تنتقد الموظف أبداً على "عدم أخذ بيانات التواصل" أو "لم يسجل الرقم/الإيميل" — البيانات موجودة أصلاً عنده.
- الاستثناء الوحيد: ليدات إعلانات ميتا (فيسبوك/انستغرام) كثيراً ما تجي أسماؤها أسماء مستعارة (نك نيم) وليست الاسم الحقيقي. لذلك راقب أمرين: (1) هل نادى الموظف العميل باسمه خلال المكالمة؟ استخدام الاسم يبني علاقة ويكشف إذا الاسم صحيح. (2) إذا اسم العميل في النظام يبدو اسماً مستعاراً (لقب مثل "أبو أحمد"، كلمة واحدة غريبة، حروف عشوائية، اسم غير حقيقي) أو ظهر خلال المكالمة أن الاسم غير مطابق — ضع توصية صريحة أن يتأكد من الاسم الحقيقي بلطف ويحدّثه بالنظام، مثلاً: "قل: حتى أخدمك أفضل، شو أحب الأسماء إلك أستاذ؟ / بمين أتشرف؟".
- جودة الشبكة/الصوت من طرف العميل ليست ذنب الموظف: لا تُنزّل تقييم الموظف بسبب ضعف شبكة العميل أو تقطّع/صدى/عدم وضوح الصوت أو الانقطاع من جهة العميل. ميّز بين خلل تقني من جهة العميل (لا يُحاسب عليه الموظف) وخلل من خط/سماعة الموظف نفسه (يوضع في flags/urgent). قيّم الموظف فقط على ما كان بمقدوره التحكم فيه، وإذا تعاملَ بلباقة مع رداءة الاتصال (طلب إعادة، أكّد الفهم) اعتبرها نقطة قوة.
- تكيّف الموظف مع مستوى العميل مطلوب لا يُعاقَب عليه: إذا كانت المكالمة متابعة (follow-up) وكان العميل واضحاً أنه متمرّس/مطّلع على الأساسيات (له خبرة تداول أو تجارة، أو صرّح أن النقاط التدريبية بديهية له)، فلا تحاسب الموظف على عدم إعادة شرح الأساسيات — فتخطّي المعروف للعميل سلوك صحيح. قيّم المتابعة بما يناسب مستوى هذا العميل: هل أضاف قيمة جديدة تناسب خبرته؟ هل تقدّم بالعلاقة نحو خطوة ملموسة؟ لا تُنزّل الدرجة لأنه لم يغطِّ نقاطاً يعرفها العميل مسبقاً.

أعد التقرير بصيغة JSON فقط (بدون أي نص خارج الـ JSON) بالحقول التالية، وكل النصوص بالعربية:

{
 "summary": "سطر واحد: شو صار بالمكالمة ونتيجتها",
 "analysis": "3-5 جمل: تحليل مجرى المكالمة — كيف بدأت، أهم لحظة/منعطف فيها (اعتراض، إشارة اهتمام، خطأ)، كيف تصرف الموظف عندها، وشو كانت النتيجة النهائية ولماذا",
 "outcome": "interested | follow_up | not_interested | callback | complaint | no_conversation | other",
 "score": 0-10 رقم بفاصلة واحدة (تقييم أداء الموظف),
 "priority": "critical | urgent | medium | normal",
 "strengths": ["نقطة قوة محددة مع مثال من المكالمة", "..."] (حد أقصى 3، إذا ما في اكتب []),
 "weaknesses": ["نقطة ضعف محددة مع مثال من المكالمة", "..."] (حد أقصى 3),
 "recommendation": "أهم توصية عملية واحدة أو اثنتين — أول شي يغيّره الموظف بمكالمته الجاية",
 "flags": ["مخالفة/إشارة مهمة مع اقتباس"] (فقط إن وجدت، وإلا []),
 "coaching": {
   "opening": "3-4 جمل تدريبية عن الافتتاحية بما يناسب نوع المكالمة: في المكالمة الأولى (تحية دافئة، تعريف بالاسم والشركة، مناداة العميل باسمه، سبب اتصال واضح ومشوّق، سؤال إذن بالوقت)؛ وفي المتابعة (ترحيب بالاسم + ربط بآخر تواصل وما اتُّفق عليه + سبب مكالمة اليوم — بدون إعادة تعريف بالشركة). شو عمل الموظف فعلياً، شو الصح، ثم صيغة حرفية جاهزة يفتتح فيها مكالمته الجاية: قل: ...",
   "middle": "3-4 جمل تدريبية عن وسط المكالمة بما يناسب نوع المكالمة: بالمكالمة الأولى أسئلة الاكتشاف (وضعه، خبرته، هدفه، رأس ماله المريح)؛ وبالمتابعة البناء على المعروف مسبقاً وإضافة قيمة جديدة بدل إعادة الأسئلة. هل أصغى أكثر مما حكى؟ هل ربط العرض بحاجة العميل نفسه؟ كيف عالج الاعتراضات (يتفهم أولاً ثم يجاوب)؟ أعطِ مثالاً حرفياً لسؤال أو رد كان لازم يقوله: قل: ...",
   "closing": "3-4 جمل تدريبية عن الإغلاق: هل لخّص الاتفاق؟ هل حدد خطوة تالية ملموسة بموعد محدد (يوم وساعة) بدل عبارات مفتوحة مثل إن شاء الله/على وقتك؟ هل الالتزام صار من طرف الموظف (أنا رح أتصل فيك) وليس معلقاً على مبادرة العميل؟ أعطِ صيغة إغلاق حرفية مناسبة لهذه المكالمة بالذات: قل: ..."
 }
}

قواعد الـ coaching — هذا أهم جزء بالتقرير:
- اربط كل ملاحظة بشيء صار فعلاً في هذه المكالمة (اقتبس أو أشر للحظة المحددة)، لا تكتب كلاماً عاماً يصلح لأي مكالمة.
- في كل مرحلة أعطِ صيغة حرفية جاهزة يحفظها الموظف وتناسب هذا العميل بالذات (باسمه ووضعه)، تبدأ بـ "قل: ...".
- إذا المكالمة كانت ممتازة بمرحلة معينة، قل ذلك صراحة وثبّت السلوك الصحيح (شو بالضبط عمله صح حتى يكرره).
- إذا المكالمة قصيرة/فاشلة تقنياً، ركّز الـ coaching على كيف كان ممكن ينقذها أو شو يعمل بالمحاولة الجاية.

معايير priority — بترتيب الأهمية:
- critical: مخالفة التزام (وعد بأرباح أو نسب نجاح، كلمة ضمان/مضمون، معلومات مضللة عن المخاطر)، أو عميل غاضب يهدد بشكوى/سحب أمواله، أو شبهة احتيال. هذه لازم يقرأها المدير فوراً.
  انتبه جيداً: أي رقم أو نسبة يذكرها الموظف عن النجاح أو الربح — حتى لو عابرة أو غير مباشرة — تعتبر critical. أمثلة: "نسبة النجاح 70%"، "معظم عملائنا يربحون"، "رح تربح إن شاء الله"، "مضمون"، "ما في خسارة". افحص التفريغ بعناية عن هالنمط وأضفه في flags مع اقتباس الجملة — بشرط أن يكون معنى الجملة واضحاً من سياقها الكامل؛ إذا كانت العبارة مشوّهة أو يُحتمل أنها خطأ تفريغ فلا تجعلها مخالفة (اذكرها في analysis كاحتمال إن كانت مهمة، بدون flag وبدون critical).
- urgent: عميل جاهز للإيداع أو مهتم جداً ويحتاج متابعة فورية، أو شكوى جدية، أو سوء تعامل واضح من الموظف، أو عطل تقني واضح بخط/سماعة الموظف يضيع المكالمات (مثل تكرار "ألو/مرحبا" بدون محادثة).
  ملاحظة: العطل التقني أو المكالمة الفاشلة ليست critical — الـ critical حصراً للمخالفات والغضب والاحتيال.
- medium: مشاكل أداء ملحوظة تحتاج تدريب (إغلاق ضعيف، ضياع فرصة واضحة، ما استخدم اسم العميل، ما سأل أسئلة اكتشاف).
- normal: مكالمة روتينية ما فيها شي يستدعي مراجعة المدير.

قواعد التقييم (score): افتتاحية وتعريف واضح ومناداة العميل باسمه، أسئلة اكتشاف وإصغاء (نسبة كلام العميل)، ربط العرض بحاجة العميل، معالجة الاعتراضات، خطوة تالية ملموسة بموعد محدد (وليس "إن شاء الله")، الالتزام (لا وعود أرباح ولا ضمانات). لا تحاسب على جمع بيانات التواصل — موجودة بالنظام. مكالمة بدون محادثة فعلية (ما رد/انقطعت): score حسب المتاح و outcome=no_conversation و priority=normal."""


def _api_key():
    with open(KEY_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()


def score_call(transcript_text, meta):
    import anthropic
    client = anthropic.Anthropic(api_key=_api_key())
    # prior recorded calls with this number -> the model can tell a FIRST call from a FOLLOW-UP
    # and coach accordingly (#226/#218). History is best-effort (only what we QA'd).
    hist = meta.get("history") or []
    if hist:
        lines = "\n".join(
            f"  - {h.get('when','؟')} مع {h.get('agent') or 'موظف'} — النتيجة: {h.get('outcome') or '؟'}"
            + (f" — {h['summary']}" if h.get("summary") else "")
            for h in hist)
        hist_txt = (f"سجل المكالمات المسجلة سابقاً مع هذا الرقم (الأحدث أولاً — أي أن هذه مكالمة متابعة):\n{lines}")
    else:
        hist_txt = ("لا توجد مكالمات مسجلة سابقاً مع هذا الرقم عندنا — قد تكون هذه أول مكالمة؛ "
                    "وإن دلّ الحديث نفسه على معرفة سابقة فاعتبرها متابعة.")
    user_msg = (f"الموظف: {meta.get('agent_name')} (تحويلة {meta.get('agent_ext')})\n"
                f"الاتجاه: {meta.get('direction')} | المدة: {meta.get('duration')} ثانية\n"
                f"العميل بالنظام: {meta.get('crm_note') or 'غير معروف'}\n"
                f"{hist_txt}\n\n"
                f"التفريغ:\n{transcript_text}")

    def _ask(max_tok):
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tok,
            system=SCORING_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = "".join(b.text for b in resp.content if b.type == "text")
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            raise ValueError(f"no JSON in model reply: {raw[:200]}")
        # strict=False: tolerate literal newlines/tabs the model sometimes emits inside strings
        return json.loads(m.group(0), strict=False)

    try:
        rep = _ask(3000)
    except (ValueError, json.JSONDecodeError):
        rep = _ask(4000)          # long reply got truncated — retry with more room
    rep["priority"] = str(rep.get("priority", "normal")).lower()
    if rep["priority"] not in ("critical", "urgent", "medium", "normal"):
        rep["priority"] = "normal"
    try:
        rep["score"] = round(float(rep.get("score", 0)), 1)
    except Exception:
        rep["score"] = None
    return rep


# ---------------------------------------------------------------- DB helpers

def ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS call_qa (
            id              SERIAL PRIMARY KEY,
            recording_id    BIGINT UNIQUE NOT NULL,
            uid             TEXT,
            call_time       TIMESTAMPTZ,
            agent_ext       TEXT,
            agent_name      TEXT,
            customer_number TEXT,
            direction       TEXT,
            duration        INT,
            client_login    BIGINT,
            client_name     TEXT,
            language        TEXT,
            transcript_text TEXT,
            segments        JSONB,
            summary         TEXT,
            outcome         TEXT,
            score           NUMERIC(3,1),
            priority        TEXT,
            strengths       JSONB,
            weaknesses      JSONB,
            recommendation  TEXT,
            flags           JSONB,
            created_at      TIMESTAMPTZ DEFAULT NOW()
        )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_call_qa_agent ON call_qa(agent_ext, call_time DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_call_qa_priority ON call_qa(priority, call_time DESC)")
    cur.execute("ALTER TABLE call_qa ADD COLUMN IF NOT EXISTS contact_type TEXT")
    cur.execute("ALTER TABLE call_qa ADD COLUMN IF NOT EXISTS coaching JSONB")
    cur.execute("ALTER TABLE call_qa ADD COLUMN IF NOT EXISTS analysis TEXT")
    cur.execute("ALTER TABLE call_qa ADD COLUMN IF NOT EXISTS read_at TIMESTAMPTZ")
    cur.execute("ALTER TABLE call_qa ADD COLUMN IF NOT EXISTS read_by TEXT")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_call_qa_customer ON call_qa(customer_number, call_time DESC)")


def lookup_customer(cur, number):
    """Resolve a phone number to (login, name, contact_type).
    contact_type: 'ib' (the person's own account is an IB), 'client', 'lead', or None."""
    digits = re.sub(r"\D", "", number or "")
    if len(digits) < 9:
        return None, None, None
    tail = digits[-9:]
    cur.execute("""SELECT login, name FROM clients
                   WHERE RIGHT(REGEXP_REPLACE(COALESCE(phone,''), '\\D', '', 'g'), 9) = %s
                   LIMIT 1""", (tail,))
    row = cur.fetchone()
    if row:
        login, name = row
        cur.execute("SELECT 1 FROM ibs WHERE agent_id = %s LIMIT 1", (login,))
        return login, name, ("ib" if cur.fetchone() else "client")
    cur.execute("""SELECT id, full_name FROM leads
                   WHERE RIGHT(REGEXP_REPLACE(COALESCE(phone,''), '\\D', '', 'g'), 9) = %s
                   LIMIT 1""", (tail,))
    row = cur.fetchone()
    if row:
        return None, row[1], "lead"
    return None, None, None


# ------------------------------------------------------------------- driver

def run_cycle(hours, limit):
    conn = db_config.connect()
    conn.autocommit = True
    cur = conn.cursor()
    ensure_table(cur)

    recs, tok = fetch_recent_recordings(hours)
    _log(f"PBX recordings in last {hours}h: {len(recs)}")

    cur.execute("SELECT recording_id FROM call_qa WHERE call_time > NOW() - INTERVAL '60 days'")
    done = {r[0] for r in cur.fetchall()}

    todo = [r for r in recs
            if r["id"] not in done and MIN_DURATION <= (r.get("duration") or 0) <= MAX_DURATION]
    if SHARD is not None:                       # split work across parallel backfill workers
        k, m = SHARD
        todo = [r for r in todo if r["id"] % m == k]
    todo.sort(key=lambda r: r["_ts"])          # oldest first so reports appear in order
    if limit:
        todo = todo[:limit]
    _log(f"to process: {len(todo)}")

    n_ok = n_err = 0
    for rec in todo:
        rid = rec["id"]
        try:
            t0 = time.time()
            wav = download_recording(rec, tok)
            text, segs, lang = transcribe(wav)
            login, cname, ctype = lookup_customer(cur, rec.get("call_to_number")
                                                  if rec.get("call_type") == "Outbound"
                                                  else rec.get("call_from_number"))
            agent_ext = rec.get("call_from_number") if rec.get("call_type") == "Outbound" \
                else rec.get("call_to_number")
            agent_name = rec.get("call_from_name") if rec.get("call_type") == "Outbound" \
                else rec.get("call_to_name")
            customer = rec.get("call_to_number") if rec.get("call_type") == "Outbound" \
                else rec.get("call_from_number")
            # prior QA'd calls with this number (before this call) — lets the scorer distinguish a
            # first call from a follow-up and evaluate continuity instead of intro-call rubric (#226)
            history = []
            try:
                cur.execute("""SELECT call_time, agent_name, outcome, summary FROM call_qa
                               WHERE customer_number = %s AND call_time < %s
                               ORDER BY call_time DESC LIMIT 3""",
                            (customer, datetime.fromtimestamp(rec["_ts"])))
                history = [{"when": str(h[0])[:16], "agent": h[1], "outcome": h[2],
                            "summary": (h[3] or "")[:160]} for h in cur.fetchall()]
            except Exception:
                pass
            meta = {
                "agent_ext": agent_ext, "agent_name": agent_name,
                "direction": rec.get("call_type"), "duration": rec.get("duration"),
                "crm_note": (f"{'وكيل IB' if ctype == 'ib' else 'عميل مسجل'} login {login} - {cname}"
                             if login else (f"ليد: {cname}" if cname else None)),
                "history": history,
            }
            rep = score_call(text, meta)
            cur.execute("""
                INSERT INTO call_qa (recording_id, uid, call_time, agent_ext, agent_name,
                    customer_number, direction, duration, client_login, client_name,
                    contact_type, language, transcript_text, segments, summary, analysis,
                    outcome, score, priority, strengths, weaknesses, recommendation, flags, coaching)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (recording_id) DO NOTHING
            """, (rid, rec.get("uid"),
                  datetime.fromtimestamp(rec["_ts"]),
                  agent_ext, agent_name, customer, rec.get("call_type"),
                  rec.get("duration"), login, cname, ctype, lang, text,
                  json.dumps(segs, ensure_ascii=False),
                  rep.get("summary"), rep.get("analysis"), rep.get("outcome"),
                  rep.get("score"), rep.get("priority"),
                  json.dumps(rep.get("strengths") or [], ensure_ascii=False),
                  json.dumps(rep.get("weaknesses") or [], ensure_ascii=False),
                  rep.get("recommendation"),
                  json.dumps(rep.get("flags") or [], ensure_ascii=False),
                  json.dumps(rep.get("coaching") or {}, ensure_ascii=False)))
            try:
                os.remove(wav)
            except OSError:
                pass
            n_ok += 1
            _log(f"#{rid} {agent_name} -> score {rep.get('score')} {rep.get('priority')} "
                 f"({time.time()-t0:.0f}s)")
        except Exception as e:
            n_err += 1
            _log(f"#{rid} FAILED: {e}")
    _log(f"cycle done: {n_ok} ok, {n_err} failed")
    conn.close()
    return n_ok, n_err


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--loop", action="store_true", help="run forever, every 10 min")
    ap.add_argument("--interval", type=int, default=600)
    ap.add_argument("--shard", default=None, metavar="K/M",
                    help="process only recordings where id %% M == K (parallel workers), e.g. 0/3")
    args = ap.parse_args()
    if args.shard:
        k, m = args.shard.split("/")
        SHARD = (int(k), int(m))
    if args.loop:
        while True:
            try:
                run_cycle(args.hours, args.limit)
            except Exception as e:
                _log(f"cycle error: {e}")
            time.sleep(args.interval)
    else:
        run_cycle(args.hours, args.limit)
