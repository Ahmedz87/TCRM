/* ibI18n.ts — partner-portal translations. EN / AR / TR / KU (Kurdish Sorani).
   AR + KU are RTL. Usage: const t = ibT(lang); t('nav.dashboard').
   Missing keys fall back to English, so partial coverage never breaks the UI. */

export type Lang = 'en' | 'ar' | 'tr' | 'ku' | 'fa' | 'ur';
export const IB_LANGS: { k: Lang; label: string; flag: string; rtl: boolean }[] = [
  { k: 'en', label: 'English',  flag: '🇬🇧', rtl: false },
  { k: 'ar', label: 'العربية',  flag: '🇸🇦', rtl: true },
  // Kurdistan flag (no unicode emoji exists) — inline SVG: red / white+sun / green
  { k: 'ku', label: 'کوردی', rtl: true,
    flag: "data:image/svg+xml;utf8," + encodeURIComponent(
      "<svg xmlns='http://www.w3.org/2000/svg' width='21' height='15' viewBox='0 0 21 15'><rect width='21' height='15' fill='#fff'/><rect width='21' height='5' fill='#ED2939'/><rect y='10' width='21' height='5' fill='#28A745'/><g fill='#FEBE10'><circle cx='10.5' cy='7.5' r='2.4'/></g></svg>") },
  { k: 'fa', label: 'فارسی',    flag: '🇮🇷', rtl: true },
  { k: 'ur', label: 'اردو',     flag: '🇵🇰', rtl: true },
  { k: 'tr', label: 'Türkçe',   flag: '🇹🇷', rtl: false },
];
export const isRTL = (l: Lang) => l === 'ar' || l === 'ku' || l === 'fa' || l === 'ur';

// Which languages to OFFER an IB, based on their country — always English + the local one(s).
// (Iraq → Kurdish + Arabic + English; Iran → Persian; Pakistan → Urdu; Turkey → Turkish; …)
const COUNTRY_LANGS: { match: string[]; langs: Lang[] }[] = [
  { match: ['iraq', 'iq', 'kurd', 'کوردستان', 'العراق'], langs: ['ku', 'ar'] },
  { match: ['iran', 'ir', 'persia', 'ایران'], langs: ['fa'] },
  { match: ['afghan', 'af'], langs: ['fa', 'ur'] },
  { match: ['pakistan', 'pk', 'india', 'in', 'bangladesh', 'bd', 'پاکستان'], langs: ['ur'] },
  { match: ['turkey', 'türkiye', 'turkiye', 'tr'], langs: ['tr'] },
  { match: ['saudi', 'emirat', 'uae', 'ae', 'egypt', 'jordan', 'kuwait', 'qatar', 'bahrain',
            'oman', 'leban', 'syria', 'yemen', 'libya', 'morocc', 'tunis', 'algeri', 'sudan',
            'palest', 'sa', 'eg', 'jo', 'kw', 'qa', 'العربية'], langs: ['ar'] },
];
export function langsForCountry(country?: string): Lang[] {
  const c = (country || '').trim().toLowerCase();
  const found = c ? COUNTRY_LANGS.find(x => x.match.some(m => c.includes(m))) : null;
  const locals: Lang[] = found ? found.langs : ['ar'];   // MENA-default to Arabic when unknown
  return ['en', ...locals];                              // English always available
}

const EN: Record<string, string> = {
  'nav.dashboard': 'Dashboard', 'nav.clients': 'Trading accounts', 'nav.leads': 'Leads',
  'nav.trades': 'Trades', 'nav.campaigns': 'Campaigns', 'nav.challenges': 'Challenges',
  'nav.subibs': 'Sub-IBs', 'nav.marketing': 'Banners', 'nav.earnings': 'Earnings', 'nav.profile': 'Profile',
  'nav.leaderboard': 'Leaderboard',
  'kpi.leads': 'Leads', 'kpi.clients': 'Clients', 'kpi.nda': 'New Clients', 'kpi.commission': 'Commission',
  'kpi.available': 'Available to withdraw', 'kpi.paid': 'Paid out', 'kpi.earned': 'Total earned', 'kpi.rate': 'Rate',
  'kpi.leads_sub': 'registered · no deposit yet', 'kpi.nda_sub': 'counted for promotion / total',
  'kpi.active': 'active', 'kpi.archived': 'archived', 'kpi.earned_pre': 'lifetime earned',
  'kpi.nda_info_title': 'NDA — New Deposit Account',
  'kpi.nda_info_body': 'An NDA is a client who made their FIRST deposit through you. The second number ({total}) is the total of those who deposited with you; the first number ({new}) are the genuinely-new ones — they count toward your promotions and challenges.',
  'btn.withdraw': 'Withdraw', 'btn.transfer': 'Internal transfer', 'btn.copy': 'Copy', 'btn.copied': 'Copied',
  'btn.save': 'Save', 'btn.statement': 'Statement (CSV)', 'btn.qr': 'QR code',
  'earn.payouts': 'Payouts', 'ref.title': 'Your referral link',
  'ref.share': 'Share this everywhere — every signup through it is credited to you automatically.',
  'ref.unique': 'unique clicks', 'ref.total': 'total clicks', 'ref.signups': 'signups',
  'notif.title': 'Notifications', 'notif.empty': 'Nothing yet.',
  'lead.title': 'Your leads — registered under you but no deposit yet. Call them and follow up.',
  'status.nda': 'New Client', 'status.ftd': 'Related', 'status.additional': 'Additional', 'status.review': 'Under review',
  'promo.unlock': 'To unlock', 'promo.deposits': 'Deposits', 'promo.lots': 'Lots · monthly average', 'promo.new': 'New clients',
};
const AR: Record<string, string> = {
  'nav.dashboard': 'الرئيسية', 'nav.clients': 'الحسابات', 'nav.leads': 'العملاء المحتملون',
  'nav.trades': 'الصفقات', 'nav.campaigns': 'الحملات', 'nav.challenges': 'التحديات',
  'nav.subibs': 'الوسطاء الفرعيون', 'nav.marketing': 'البانرات', 'nav.earnings': 'الأرباح', 'nav.profile': 'الملف',
  'nav.leaderboard': 'المتصدرون',
  'kpi.leads': 'العملاء المحتملون', 'kpi.clients': 'العملاء', 'kpi.nda': 'عملاء جدد', 'kpi.commission': 'العمولة',
  'kpi.available': 'متاح للسحب', 'kpi.paid': 'المدفوع', 'kpi.earned': 'إجمالي الأرباح', 'kpi.rate': 'المعدل',
  'kpi.leads_sub': 'مسجّل · لم يودع بعد', 'kpi.nda_sub': 'المحتسب للترقية / الإجمالي',
  'kpi.active': 'نشط', 'kpi.archived': 'مؤرشف', 'kpi.earned_pre': 'إجمالي الأرباح',
  'kpi.nda_info_title': 'NDA — حساب إيداع جديد',
  'kpi.nda_info_body': 'الـ NDA هو عميل قام بأول إيداع له من خلالك. الرقم الثاني ({total}) هو إجمالي من أودعوا معك؛ والرقم الأول ({new}) هم العملاء الجدد فعلاً — وهم من يُحتسبون لترقياتك وتحدياتك.',
  'btn.withdraw': 'سحب', 'btn.transfer': 'تحويل داخلي', 'btn.copy': 'نسخ', 'btn.copied': 'تم النسخ',
  'btn.save': 'حفظ', 'btn.statement': 'كشف الحساب (CSV)', 'btn.qr': 'رمز QR',
  'earn.payouts': 'المدفوعات', 'ref.title': 'رابط الإحالة الخاص بك',
  'ref.share': 'شاركه في كل مكان — كل تسجيل عبره يُحتسب لك تلقائياً.',
  'ref.unique': 'نقرات فريدة', 'ref.total': 'إجمالي النقرات', 'ref.signups': 'تسجيلات',
  'notif.title': 'الإشعارات', 'notif.empty': 'لا شيء بعد.',
  'lead.title': 'عملاؤك المحتملون — مسجّلون تحتك بدون إيداع بعد. اتصل بهم وتابعهم.',
  'status.nda': 'جديد', 'status.ftd': 'إيداع أول', 'status.additional': 'حساب إضافي', 'status.review': 'قيد المراجعة',
  'promo.unlock': 'للترقية إلى', 'promo.deposits': 'الإيداعات', 'promo.lots': 'اللوتات · المعدل الشهري', 'promo.new': 'عملاء جدد',
};
const TR: Record<string, string> = {
  'nav.dashboard': 'Panel', 'nav.clients': 'İşlem hesapları', 'nav.leads': 'Adaylar',
  'nav.trades': 'İşlemler', 'nav.campaigns': 'Kampanyalar', 'nav.challenges': 'Görevler',
  'nav.subibs': 'Alt-IB\'ler', 'nav.marketing': 'Banner\'lar', 'nav.earnings': 'Kazançlar', 'nav.profile': 'Profil',
  'nav.leaderboard': 'Lider tablosu',
  'kpi.leads': 'Adaylar', 'kpi.clients': 'Müşteriler', 'kpi.nda': 'Yeni Müşteriler', 'kpi.commission': 'Komisyon',
  'kpi.available': 'Çekilebilir', 'kpi.paid': 'Ödenen', 'kpi.earned': 'Toplam kazanç', 'kpi.rate': 'Oran',
  'kpi.leads_sub': 'kayıtlı · henüz yatırım yok', 'kpi.nda_sub': 'terfi için sayılan / toplam',
  'kpi.active': 'aktif', 'kpi.archived': 'arşivli', 'kpi.earned_pre': 'toplam kazanç',
  'kpi.nda_info_title': 'NDA — Yeni Mevduat Hesabı',
  'kpi.nda_info_body': 'NDA, ilk yatırımını sizin aracılığınızla yapan bir müşteridir. İkinci sayı ({total}) sizinle yatırım yapanların toplamıdır; ilk sayı ({new}) gerçekten yeni olanlardır — terfileriniz ve görevleriniz için sayılanlar bunlardır.',
  'btn.withdraw': 'Çek', 'btn.transfer': 'İç transfer', 'btn.copy': 'Kopyala', 'btn.copied': 'Kopyalandı',
  'btn.save': 'Kaydet', 'btn.statement': 'Ekstre (CSV)', 'btn.qr': 'QR kodu',
  'earn.payouts': 'Ödemeler', 'ref.title': 'Referans bağlantınız',
  'ref.share': 'Her yerde paylaşın — üzerinden gelen her kayıt otomatik size sayılır.',
  'ref.unique': 'benzersiz tıklama', 'ref.total': 'toplam tıklama', 'ref.signups': 'kayıt',
  'notif.title': 'Bildirimler', 'notif.empty': 'Henüz yok.',
  'lead.title': 'Adaylarınız — size kayıtlı ama henüz yatırım yapmadı. Arayın ve takip edin.',
  'status.nda': 'Yeni Müşteri', 'status.ftd': 'İlişkili', 'status.additional': 'Ek hesap', 'status.review': 'İncelemede',
  'promo.unlock': 'Yükselmek için', 'promo.deposits': 'Yatırımlar', 'promo.lots': 'Lot · aylık ortalama', 'promo.new': 'Yeni müşteriler',
};
const KU: Record<string, string> = {
  'nav.dashboard': 'داشبۆرد', 'nav.clients': 'هەژمارەکان', 'nav.leads': 'کڕیارە چاوەڕوانەکان',
  'nav.trades': 'مامەڵەکان', 'nav.campaigns': 'کەمپینەکان', 'nav.challenges': 'ئەرکەکان',
  'nav.subibs': 'ژێر-IB', 'nav.marketing': 'بانەرەکان', 'nav.earnings': 'داهاتەکان', 'nav.profile': 'پرۆفایل',
  'nav.leaderboard': 'ڕیزبەندی',
  'kpi.leads': 'کڕیارە چاوەڕوانەکان', 'kpi.clients': 'کڕیارەکان', 'kpi.nda': 'کڕیارە نوێیەکان', 'kpi.commission': 'کۆمیشن',
  'kpi.available': 'بەردەست بۆ کێشانەوە', 'kpi.paid': 'دراوە', 'kpi.earned': 'کۆی داهات', 'kpi.rate': 'ڕێژە',
  'kpi.leads_sub': 'تۆمارکراو · هێشتا پارە دانەنراوە', 'kpi.nda_sub': 'ژمێردراو بۆ بەرزکردنەوە / کۆ',
  'kpi.active': 'چالاک', 'kpi.archived': 'ئەرشیفکراو', 'kpi.earned_pre': 'کۆی داهات',
  'kpi.nda_info_title': 'NDA — هەژماری پارەدانی نوێ',
  'kpi.nda_info_body': 'NDA کڕیارێکە کە یەکەم پارەدانی لە ڕێگەی تۆوە کردووە. ژمارەی دووەم ({total}) کۆی ئەوانەیە کە پارەیان لەلای تۆ داناوە؛ ژمارەی یەکەم ({new}) ئەوانەن کە بەڕاستی نوێن — ئەوانەن کە بۆ بەرزکردنەوە و ململانێکانت دەژمێردرێن.',
  'btn.withdraw': 'کێشانەوە', 'btn.transfer': 'گواستنەوەی ناوخۆیی', 'btn.copy': 'کۆپی', 'btn.copied': 'کۆپیکرا',
  'btn.save': 'پاشەکەوت', 'btn.statement': 'کەشف (CSV)', 'btn.qr': 'کۆدی QR',
  'earn.payouts': 'پارەدانەکان', 'ref.title': 'بەستەری ئاماژەکەت',
  'ref.share': 'لە هەموو شوێنێک بڵاوی بکەرەوە — هەر تۆمارکردنێک لە ڕێگایەوە بۆ تۆ ژمێردەکرێت.',
  'ref.unique': 'کلیکی بێهاوتا', 'ref.total': 'کۆی کلیک', 'ref.signups': 'تۆمارکردن',
  'notif.title': 'ئاگادارییەکان', 'notif.empty': 'هێشتا هیچ نییە.',
  'lead.title': 'کڕیارە چاوەڕوانەکانت — لەژێر تۆ تۆمارکراون بەڵام هێشتا سپاردەیان نەکردووە. پەیوەندییان پێوە بکە.',
  'status.nda': 'نوێ', 'status.ftd': 'FTD', 'status.additional': 'هەژماری زیادە', 'status.review': 'لە پێداچوونەوەدا',
  'promo.unlock': 'بۆ چوونەسەرەوە بۆ', 'promo.deposits': 'سپاردەکان', 'promo.lots': 'لۆت · تێکڕای مانگانە', 'promo.new': 'کڕیارە نوێیەکان',
};

const FA: Record<string, string> = {
  'nav.dashboard': 'داشبورد', 'nav.clients': 'حساب‌های معاملاتی', 'nav.leads': 'سرنخ‌ها',
  'nav.trades': 'معاملات', 'nav.campaigns': 'کمپین‌ها', 'nav.challenges': 'چالش‌ها',
  'nav.leaderboard': 'جدول برترین‌ها', 'nav.subibs': 'زیرمجموعه‌ها', 'nav.marketing': 'بنرها',
  'nav.earnings': 'درآمدها', 'nav.profile': 'پروفایل',
  'kpi.leads': 'سرنخ‌ها', 'kpi.clients': 'مشتریان', 'kpi.nda': 'مشتریان جدید', 'kpi.commission': 'کمیسیون',
  'kpi.available': 'قابل برداشت', 'kpi.paid': 'پرداخت‌شده', 'kpi.earned': 'کل درآمد', 'kpi.rate': 'نرخ',
  'kpi.leads_sub': 'ثبت‌نام‌شده · هنوز واریزی ندارد', 'kpi.nda_sub': 'محاسبه‌شده برای ارتقا / کل',
  'kpi.active': 'فعال', 'kpi.archived': 'بایگانی‌شده', 'kpi.earned_pre': 'کل درآمد',
  'kpi.nda_info_title': 'NDA — حساب واریز جدید',
  'kpi.nda_info_body': 'NDA مشتری‌ای است که اولین واریز خود را از طریق شما انجام داده است. عدد دوم ({total}) کل کسانی است که با شما واریز کرده‌اند؛ عدد اول ({new}) کسانی هستند که واقعاً جدیدند — همان‌ها که برای ارتقا و چالش‌های شما محاسبه می‌شوند.',
  'btn.withdraw': 'برداشت', 'btn.transfer': 'انتقال داخلی', 'btn.copy': 'کپی', 'btn.copied': 'کپی شد',
  'btn.save': 'ذخیره', 'btn.statement': 'صورت‌حساب (CSV)', 'btn.qr': 'کد QR',
  'earn.payouts': 'پرداخت‌ها', 'ref.title': 'لینک معرف شما',
  'ref.share': 'همه‌جا به اشتراک بگذارید — هر ثبت‌نام از طریق آن به‌طور خودکار برای شما ثبت می‌شود.',
  'ref.unique': 'کلیک یکتا', 'ref.total': 'کل کلیک‌ها', 'ref.signups': 'ثبت‌نام‌ها',
  'notif.title': 'اعلان‌ها', 'notif.empty': 'هنوز چیزی نیست.',
  'lead.title': 'سرنخ‌های شما — زیر شما ثبت‌نام کرده‌اند اما هنوز واریز نکرده‌اند. با آن‌ها تماس بگیرید.',
  'status.nda': 'جدید', 'status.ftd': 'اولین واریز', 'status.additional': 'حساب اضافی', 'status.review': 'در حال بررسی',
  'promo.unlock': 'برای ارتقا به', 'promo.deposits': 'واریزها', 'promo.lots': 'لات · میانگین ماهانه', 'promo.new': 'مشتریان جدید',
};
const UR: Record<string, string> = {
  'nav.dashboard': 'ڈیش بورڈ', 'nav.clients': 'ٹریڈنگ اکاؤنٹس', 'nav.leads': 'لیڈز',
  'nav.trades': 'ٹریڈز', 'nav.campaigns': 'مہمات', 'nav.challenges': 'چیلنجز',
  'nav.leaderboard': 'لیڈر بورڈ', 'nav.subibs': 'ذیلی IBs', 'nav.marketing': 'بینرز',
  'nav.earnings': 'کمائی', 'nav.profile': 'پروفائل',
  'kpi.leads': 'لیڈز', 'kpi.clients': 'کلائنٹس', 'kpi.nda': 'نئے کلائنٹس', 'kpi.commission': 'کمیشن',
  'kpi.available': 'نکالنے کے لیے دستیاب', 'kpi.paid': 'ادا شدہ', 'kpi.earned': 'کل کمائی', 'kpi.rate': 'ریٹ',
  'kpi.leads_sub': 'رجسٹرڈ · ابھی کوئی جمع نہیں', 'kpi.nda_sub': 'ترقی کے لیے شمار / کل',
  'kpi.active': 'فعال', 'kpi.archived': 'آرکائیو شدہ', 'kpi.earned_pre': 'کل کمائی',
  'kpi.nda_info_title': 'NDA — نیا ڈپازٹ اکاؤنٹ',
  'kpi.nda_info_body': 'NDA وہ کلائنٹ ہے جس نے اپنی پہلی جمع آپ کے ذریعے کی۔ دوسرا نمبر ({total}) ان سب کا کل ہے جنہوں نے آپ کے ساتھ جمع کرایا؛ پہلا نمبر ({new}) وہ ہیں جو واقعی نئے ہیں — یہی آپ کی ترقیوں اور چیلنجز کے لیے شمار ہوتے ہیں۔',
  'btn.withdraw': 'نکالیں', 'btn.transfer': 'اندرونی منتقلی', 'btn.copy': 'کاپی', 'btn.copied': 'کاپی ہو گیا',
  'btn.save': 'محفوظ کریں', 'btn.statement': 'اسٹیٹمنٹ (CSV)', 'btn.qr': 'QR کوڈ',
  'earn.payouts': 'ادائیگیاں', 'ref.title': 'آپ کا ریفرل لنک',
  'ref.share': 'ہر جگہ شیئر کریں — اس کے ذریعے ہر سائن اپ خودکار طور پر آپ کے کھاتے میں آتا ہے۔',
  'ref.unique': 'منفرد کلکس', 'ref.total': 'کل کلکس', 'ref.signups': 'سائن اپس',
  'notif.title': 'اطلاعات', 'notif.empty': 'ابھی کچھ نہیں۔',
  'lead.title': 'آپ کی لیڈز — آپ کے تحت رجسٹرڈ لیکن ابھی تک جمع نہیں کروائی۔ انہیں کال کریں۔',
  'status.nda': 'نیا', 'status.ftd': 'پہلی جمع', 'status.additional': 'اضافی اکاؤنٹ', 'status.review': 'زیر جائزہ',
  'promo.unlock': 'ترقی کے لیے', 'promo.deposits': 'جمع', 'promo.lots': 'لاٹس · ماہانہ اوسط', 'promo.new': 'نئے کلائنٹس',
};

const DICT: Record<Lang, Record<string, string>> = { en: EN, ar: AR, tr: TR, ku: KU, fa: FA, ur: UR };

export function ibT(lang: Lang) {
  const d = DICT[lang] || EN;
  return (key: string) => d[key] || EN[key] || key;
}
