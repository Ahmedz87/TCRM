"""
mt_managers.py — central roster of MT manager logins, one dedicated connection per ROLE so
nothing ever blocks or has to be stopped:

  A  live sync     — sessions / equity / account list   (read)
  B  deals/journal — history pull + backfill            (read, heavy)
  C  provisioning  — UserAdd / credit / real deposits   (write)
  D  execution     — copy-trade order send / close      (write, high-freq)

Credentials now live in the GITIGNORED backend/mt_secrets.py (P0-6) so the secret is never
committed. This module re-exports them, so every `import mt_managers as M; M.MT5[...]` caller is
unchanged. To rotate: update mt_secrets.py only.
"""
from mt_secrets import MT5_SERVER, MT4_SERVER, MT5, MT4   # noqa: F401
