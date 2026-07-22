# -*- coding: utf-8 -*-
"""Compact inline SVG flags (16x12 viewBox) — reliable cross-platform (emoji flags fail on Windows,
and Kurdistan has no emoji). One per language's representative flag; the geo layer swaps the Arabic
flag to the detected country (IQ/AE/SA...) at runtime."""

def _svg(body):
    return ('<svg viewBox="0 0 16 12" width="18" height="13" style="border-radius:2px;display:block" '
            'aria-hidden="true">' + body + '</svg>')

# country flag bodies keyed by ISO2 (used by JS geo swap) + language default flags
FLAGS = {
  # English -> UK
  "GB": _svg('<rect width="16" height="12" fill="#012169"/><path d="M0 0l16 12M16 0L0 12" stroke="#fff" stroke-width="2.4"/><path d="M0 0l16 12M16 0L0 12" stroke="#C8102E" stroke-width="1.2"/><path d="M8 0v12M0 6h16" stroke="#fff" stroke-width="3.4"/><path d="M8 0v12M0 6h16" stroke="#C8102E" stroke-width="2"/>'),
  "US": _svg('<rect width="16" height="12" fill="#fff"/>' + ''.join(f'<rect y="{i*1.7142}" width="16" height="0.857" fill="#B22234"/>' for i in range(7)) + '<rect width="7" height="6" fill="#3C3B6E"/>'),
  "IQ": _svg('<rect width="16" height="4" fill="#CE1126"/><rect y="4" width="16" height="4" fill="#fff"/><rect y="8" width="16" height="4" fill="#000"/><text x="8" y="7.4" font-size="3.2" fill="#007A3D" text-anchor="middle" font-family="serif">الله أكبر</text>'),
  "AE": _svg('<rect width="16" height="12" fill="#fff"/><rect width="16" height="4" fill="#00843D"/><rect y="8" width="16" height="4" fill="#000"/><rect width="4.5" height="12" fill="#CE1126"/>'),
  "SA": _svg('<rect width="16" height="12" fill="#006C35"/><text x="8" y="7.6" font-size="3" fill="#fff" text-anchor="middle" font-family="serif">لا إله إلا الله</text>'),
  "KW": _svg('<rect width="16" height="4" fill="#007A3D"/><rect y="4" width="16" height="4" fill="#fff"/><rect y="8" width="16" height="4" fill="#CE1126"/><path d="M0 0l5 4v4l-5 4z" fill="#000"/>'),
  "QA": _svg('<rect width="16" height="12" fill="#8D1B3D"/><path d="M0 0h5l1.6 1.2L5 2.4l1.6 1.2L5 4.8l1.6 1.2L5 7.2l1.6 1.2L5 9.6l1.6 1.2L5 12H0z" fill="#fff"/>'),
  "BH": _svg('<rect width="16" height="12" fill="#CE1126"/><path d="M0 0h5l1.5 1.5L5 3l1.5 1.5L5 6l1.5 1.5L5 9l1.5 1.5L5 12H0z" fill="#fff"/>'),
  "OM": _svg('<rect width="16" height="12" fill="#fff"/><rect y="0" width="16" height="4" fill="#fff"/><rect y="4" width="16" height="4" fill="#DB161B"/><rect y="8" width="16" height="4" fill="#008000"/><rect width="4.5" height="12" fill="#DB161B"/>'),
  "JO": _svg('<rect width="16" height="4" fill="#000"/><rect y="4" width="16" height="4" fill="#fff"/><rect y="8" width="16" height="4" fill="#007A3D"/><path d="M0 0l6 6-6 6z" fill="#CE1126"/>'),
  "EG": _svg('<rect width="16" height="4" fill="#CE1126"/><rect y="4" width="16" height="4" fill="#fff"/><rect y="8" width="16" height="4" fill="#000"/>'),
  # Kurdistan
  "KU": _svg('<rect width="16" height="4" fill="#ED2024"/><rect y="4" width="16" height="4" fill="#fff"/><rect y="8" width="16" height="4" fill="#278E43"/><circle cx="8" cy="6" r="2.1" fill="#FEBD11"/>'),
  "TR": _svg('<rect width="16" height="12" fill="#E30A17"/><circle cx="6" cy="6" r="2.6" fill="#fff"/><circle cx="6.8" cy="6" r="2.1" fill="#E30A17"/><path d="M9.2 6l2-0.65-1.24 1.7v-2.1l1.24 1.7z" fill="#fff"/>'),
  "ID": _svg('<rect width="16" height="6" fill="#CE1126"/><rect y="6" width="16" height="6" fill="#fff"/>'),
  "VN": _svg('<rect width="16" height="12" fill="#DA251D"/><path d="M8 2.2l1.18 3.63h3.82l-3.09 2.24 1.18 3.63L8 9.48 4.91 11.72l1.18-3.63L3 5.85h3.82z" fill="#FF0"/>'),
  "ES": _svg('<rect width="16" height="12" fill="#AA151B"/><rect y="3" width="16" height="6" fill="#F1BF00"/>'),
  "MX": _svg('<rect width="16" height="12" fill="#fff"/><rect width="5.33" height="12" fill="#006847"/><rect x="10.67" width="5.33" height="12" fill="#CE1126"/>'),
  "BR": _svg('<rect width="16" height="12" fill="#009B3A"/><path d="M8 1.5L14.5 6 8 10.5 1.5 6z" fill="#FEDF00"/><circle cx="8" cy="6" r="2.3" fill="#002776"/>'),
  "TH": _svg('<rect width="16" height="12" fill="#fff"/><rect width="16" height="2" fill="#A51931"/><rect y="10" width="16" height="2" fill="#A51931"/><rect y="4" width="16" height="4" fill="#2D2A4A"/>'),
  "IN": _svg('<rect width="16" height="4" fill="#FF9933"/><rect y="4" width="16" height="4" fill="#fff"/><rect y="8" width="16" height="4" fill="#138808"/><circle cx="8" cy="6" r="1.4" fill="none" stroke="#000080" stroke-width="0.4"/>'),
  "PK": _svg('<rect width="16" height="12" fill="#01411C"/><rect width="4.3" height="12" fill="#fff"/><circle cx="10.5" cy="6" r="2.3" fill="#fff"/><circle cx="11.3" cy="6" r="1.9" fill="#01411C"/>'),
}

# language -> default flag ISO2 (fallback when geo not resolved)
LANG_FLAG = {
  "en": "GB", "ar": "IQ", "ku": "KU", "tr": "TR", "id": "ID", "vi": "VN",
  "es": "ES", "pt": "BR", "th": "TH", "hi": "IN", "ur": "PK",
}

# country (from Cloudflare loc) -> [language codes to offer in the top bar], in order.
# Every country gets its local language(s) + English. Iraq: ar, ku, en. UAE/GCC: ar, en. etc.
COUNTRY_LANGS = {
  "IQ": ["ar", "ku", "en"],
  "AE": ["ar", "en"], "SA": ["ar", "en"], "KW": ["ar", "en"], "QA": ["ar", "en"],
  "BH": ["ar", "en"], "OM": ["ar", "en"], "JO": ["ar", "en"], "EG": ["ar", "en"],
  "LB": ["ar", "en"], "SY": ["ar", "en"], "YE": ["ar", "en"], "LY": ["ar", "en"],
  "TR": ["tr", "en"],
  "ID": ["id", "en"], "VN": ["vi", "en"], "TH": ["th", "en"],
  "IN": ["hi", "en"], "PK": ["ur", "en"],
  "BR": ["pt", "en"],
  "ES": ["es", "en"], "MX": ["es", "en"], "AR": ["es", "en"], "CO": ["es", "en"],
  "CL": ["es", "en"], "PE": ["es", "en"], "VE": ["es", "en"],
}
# country -> the flag to show for the Arabic option (so Iraq shows 🇮🇶 next to العربية, UAE shows 🇦🇪)
COUNTRY_AR_FLAG = {c: c for c in ["IQ","AE","SA","KW","QA","BH","OM","JO","EG","LB","SY","YE","LY"]}
