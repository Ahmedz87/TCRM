"""
guess_lead_gender.py — best-effort gender from the lead's first name.

Meta forms here don't ask gender, so this is a HEURISTIC (not ground truth):
  1. Kunya: name starting with Abu/أبو ("father of") -> male; Umm/أم ("mother of") -> female.
  2. Dictionary of common male/female first names (Arabic script + Latin transliterations).
  3. Arabic morphology fallback: a first name ending in ة (taa marbuta) -> likely female.
Anything unresolved stays '' (unknown). Writes leads.gender_guess.

Run:  python guess_lead_gender.py          (only fills blanks)
      python guess_lead_gender.py --all     (recompute every row)
"""
import sys, re, psycopg2
import db_config

DB = dict(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME, user=db_config.DB_USER, password=db_config.DB_PASSWORD)

# --- normalise Arabic so alef/hamza variants compare equal -------------------
def norm_ar(s: str) -> str:
    s = re.sub(r"[إأآا]", "ا", s)
    s = s.replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    s = re.sub(r"[ًٌٍَُِّْـ]", "", s)   # strip diacritics + tatweel
    return s.strip()

MALE = {
    # Arabic
    "محمد","احمد","علي","حسين","حسن","محمود","مصطفى","عبدالله","عبد","يوسف","خالد","عمر",
    "ابراهيم","عباس","عمار","حيدر","سجاد","امير","مهند","حسام","سيد","قاسم","ياسر","ماهر",
    "مرتضى","جاسم","عامر","عبود","وليد","مهدي","كرار","باسل","عماد","زيد","طارق","سامر",
    "انس","بشار","فادي","حمزة","رامي","سيف","ليث","زين","نبيل","سامي","كريم","رضا","صادق",
    "علاء","طه","ناصر","فهد","سلطان","فيصل","ماجد","هيثم","اكرم","اسامة","بلال","جعفر","صلاح",
    "نزار","وسام","يحيى","ايمن","غيث","حمودي","عبدالرحمن","عبدالكريم","عبدالرزاق","عبدالحميد",
    "ابو","قصي","نور الدين","صهيب","معاذ","عدي","تيم","ريان","ادم","عثمان","صابر","منذر","باقر",
    # Latin
    "ali","ahmad","ahmed","mohammad","mohamad","mohammed","mohamed","muhammad","mahmoud",
    "mustafa","mostafa","omar","omer","hussein","hasan","hassan","khaled","khalid","alaa",
    "anas","samer","maher","fadi","ammar","abdullah","abd","abu","abo","amir","hamza","hamoudi",
    "yousef","youssef","yusuf","bashar","saleh","kaiwan","ibrahim","abbas","haidar","hayder",
    "sajjad","qasim","sayed","yaser","walid","mahdi","karrar","basel","emad","zaid","tarek",
    "sami","karim","bilal","saif","laith","nabil","majed","faisal","fahad","sultan","osama",
    "jaafar","salah","yahya","ayman","adam","othman","baqir","ridha","sadiq","rami","zain",
}
FEMALE = {
    # Arabic
    "فاطمة","عائشة","زينب","مريم","هدى","سارة","رنا","لينا","دعاء","امل","ريم","زهرة","رغد",
    "رقية","حوراء","بتول","نرجس","شهد","اسراء","ايه","الاء","نورا","سمر","سمية","رهف","ميس",
    "دانة","جنى","ربى","عبير","منى","ندى","وفاء","هبة","سعاد","سناء","غفران","زينه","روان",
    "رؤى","ميساء","هيا","ام","رزان","تالا","ملك","ساره","ياسمين","اسيل","بسمة","رودينا","لمى",
    # Latin
    "fatima","fatimah","aisha","zainab","zaynab","mariam","maryam","huda","sara","sarah",
    "rana","lina","dua","amal","reem","zahra","ruqaya","rasha","rita","lara","hala","dana",
    "jana","abeer","mona","nada","wafaa","heba","sumaya","rahaf","yasmin","aseel","malak",
    "razan","tala","ruba","ghufran","rawan","basma","lama","salma","nisreen","rouaa",
}
# truly ambiguous unisex names -> leave unknown rather than guess wrong
AMBIGUOUS = {"نور", "nour", "noor", "ضياء", "diya", "sama", "سما", "جود", "joud", "رؤيا"}

KUNYA_MALE   = ("ابو", "abu", "abo")
KUNYA_FEMALE = ("ام", "umm", "om")


def guess(full_name: str) -> str:
    if not full_name:
        return ""
    first = full_name.strip().split()[0]
    low = first.lower()
    na = norm_ar(first)
    if na in AMBIGUOUS or low in AMBIGUOUS:
        return ""
    # kunya prefixes (Abu X / Umm X)
    if low in KUNYA_MALE or na == "ابو":
        return "male"
    if na == "ام" or low in ("umm", "om"):
        return "female"
    if na in MALE or low in MALE:
        return "male"
    if na in FEMALE or low in FEMALE:
        return "female"
    # Arabic morphology: ends in taa marbuta -> usually female (skip known male like حمزة/أسامة handled above)
    if first.endswith("ة"):
        return "female"
    return ""


def main():
    overwrite = "--all" in sys.argv
    conn = psycopg2.connect(**DB); cur = conn.cursor()
    cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS gender_guess VARCHAR")
    conn.commit()
    where = "" if overwrite else "WHERE COALESCE(gender_guess,'')=''"
    cur.execute(f"SELECT id, full_name FROM leads {where}")
    rows = cur.fetchall()
    n_m = n_f = n_u = 0
    for lid, name in rows:
        g = guess(name)
        if g == "male": n_m += 1
        elif g == "female": n_f += 1
        else: n_u += 1
        cur.execute("UPDATE leads SET gender_guess=%s WHERE id=%s", (g, lid))
    conn.commit()
    total = len(rows)
    resolved = n_m + n_f
    print(f"Processed {total} lead(s):")
    print(f"   male    {n_m:>6}")
    print(f"   female  {n_f:>6}")
    print(f"   unknown {n_u:>6}")
    if total:
        print(f"   coverage (resolved): {resolved} ({100*resolved//total}%)")
    conn.close()


if __name__ == "__main__":
    main()
