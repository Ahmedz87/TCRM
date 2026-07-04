"""
mt_managers.py — central roster of MT manager logins, one dedicated connection per ROLE so
nothing ever blocks or has to be stopped:

  A  live sync     — sessions / equity / account list   (read)
  B  deals/journal — history pull + backfill            (read, heavy)
  C  provisioning  — UserAdd / credit / real deposits   (write)
  D  execution     — copy-trade order send / close      (write, high-freq)

Each function imports its (server, login, password) from here. Update in ONE place.
Connection-test status (2026-06-24): MT4-B login 1016 FAILS (rc=65) — needs correct login/pw.
"""

MT5_SERVER = "192.109.15.62:443"
MT4_SERVER = b"192.109.17.53:443"   # ctypes wants bytes

# role -> (login, password)
MT5 = {
    "A": (1025, "ZjFb!vA0"),         # live sync (existing bridge)
    "B": (1026, "Malakies@008"),     # deals -> transactions + backfill (mt5_deal_worker)
    "C": (3027, "Malakies@008"),     # provisioning + crediting
    "D": (3028, "Malakies@008"),     # copy-trade execution
}
MT4 = {
    "A": (1025, b"Aqjf0pJ"),         # live sync (existing mt4_loop)
    "B": (1026, b"Malakies@008"),    # journal pull + backfill (mt4_journal_worker)
    "C": (3027, b"Malakies@008"),    # provisioning
    "D": (3028, b"Malakies@008"),    # execution
}
