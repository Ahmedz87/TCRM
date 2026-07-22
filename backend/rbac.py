"""Role-based data visibility for the sales hierarchy.

- super_admin / admin / director  -> see ALL data (returns None = no filter)
- sales_manager / team leader      -> see SELF + ALL descendants (recursive subtree)
- sales_agent                      -> see SELF only

Hierarchy is encoded in users.manager_id (agent -> team leader -> sales manager -> director).
Clients/leads are linked to an agent via assigned_agent_id.

PER-USER OVERRIDES (Jul 2026 — desk can customise each leader/manager):
- users.scope_mode      'team' (default: self+descendants) | 'self' (only own book) | 'none' (sees nothing)
- users.scope_sections  comma list of the pages a leader may see: clients,leads,ibs,calls
                        (empty = all sections). e.g. a team leader limited to 'clients,leads'
                        gets an EMPTY scope on the IB / Calls pages.
- own=True (per-request) forces SELF-ONLY regardless of scope_mode — powers the "My own data"
  toggle button on each list page (a team leader momentarily narrows to just their own records).
"""
from sqlalchemy import text

# Roles that see ALL client data (no agent-scoping). Sales/retention are the exception:
# they are scoped to their own/team book. Ops roles work across the whole client base.
ALL_ACCESS_ROLES = {"super_admin", "admin", "director",
                    "backoffice", "validation", "customer_care", "vps", "marketing"}

SECTIONS = ("clients", "leads", "ibs", "calls")


def _role(user):
    r = getattr(user, "role", None)
    r = r.value if hasattr(r, "value") else r
    return (r or "").lower()


# Desk rule (Jul 2026): ONLY admins and Rahaf may change a lead/client/IB's sales agent.
# Admin-level roles qualify by role; anyone else must be explicitly granted the
# users.can_reassign_agent flag (currently just Rahaf). Single source of truth for every
# reassignment endpoint + the /auth/me flag the frontend reads to show the control.
def may_reassign_agent(user) -> bool:
    if _role(user) in ("super_admin", "admin", "director"):
        return True
    return bool(getattr(user, "can_reassign_agent", False))


def _overrides(db, uid):
    """(scope_mode, scope_sections_set) for a user; tolerant if the columns don't exist yet."""
    try:
        row = db.execute(text(
            "SELECT COALESCE(scope_mode,''), COALESCE(scope_sections,'') FROM users WHERE id=:id"
        ), {"id": uid}).fetchone()
    except Exception:
        db.rollback()
        return "team", set()
    if not row:
        return "team", set()
    mode = (row[0] or "team").strip().lower()
    secs = {s.strip().lower() for s in (row[1] or "").split(",") if s.strip()}
    return (mode if mode in ("team", "self", "none") else "team"), secs


def scope_agent_ids(db, user, section=None, own=False, recursive=False):
    """List of user ids whose clients/leads/IBs this user may see, or None for full access.

    section: one of SECTIONS — if the user's scope_sections restricts them and this page isn't
             allowed, returns [] (they see nothing here).
    own:     force self-only (the "My own data" toggle), ignoring the team subtree.
    recursive: True = self + ALL descendants (legacy). Default False = DIRECT reports only
             (desk rule Jul 2026 — a manager doesn't see her team-leaders' members).
    """
    # all-access role AND not narrowing -> full visibility (unchanged legacy behaviour)
    if _role(user) in ALL_ACCESS_ROLES and not own:
        return None

    mode, secs = _overrides(db, user.id)

    # section not permitted for this restricted leader -> empty (sees nothing on that page).
    # (all-access roles have no scope_sections, so this never fires for them.)
    if section and secs and section.lower() not in secs:
        return []
    # leader explicitly set to "sees nothing"
    if mode == "none":
        return []
    # self-only: the "My own data" toggle, or a leader pinned to their own book. `own` narrows
    # for EVERYONE (incl. all-access) so the toggle actually works when it's shown; it can only
    # ever restrict to the user's own id, never widen.
    if own or mode == "self":
        return [user.id]

    if recursive:
        rows = db.execute(text("""
            WITH RECURSIVE sub AS (
                SELECT id FROM users WHERE id = :uid
                UNION ALL
                SELECT u.id FROM users u JOIN sub ON u.manager_id = sub.id
            )
            SELECT id FROM sub
        """), {"uid": user.id}).fetchall()
    else:
        # DIRECT reports only (self + immediate children) — the desk rule everywhere.
        rows = db.execute(text(
            "SELECT id FROM users WHERE id = :uid OR manager_id = :uid"), {"uid": user.id}).fetchall()
    return [r[0] for r in rows]


def visible_agent_ids(db, user):
    """Agent ids visible on the SALES-TEAM pages (Sales Agents / its KPIs), DIRECT-REPORTS model:
      • admin / director / all-access ops roles -> None (every agent)
      • sales_manager or a team-leader (has reports) -> SELF + DIRECT children only
        (manager_id = self). NOT the whole recursive subtree — a manager does NOT see the
        members inside her team-leaders' teams (desk rule, Jul 2026 — Ayat's case).
      • sales_agent / retention agent -> SELF only
    Returns None (all) or a list of ids.
    """
    if _role(user) in ALL_ACCESS_ROLES:
        return None
    mode, _ = _overrides(db, user.id)
    if mode == "none":
        return []
    if mode == "self":
        return [user.id]
    kids = db.execute(text("SELECT id FROM users WHERE manager_id = :uid"), {"uid": user.id}).fetchall()
    if kids:                                   # leads a team -> self + direct reports
        return [user.id] + [r[0] for r in kids]
    return [user.id]                           # plain agent -> self only


def section_allowed(db, user, section):
    """True if `user` may see `section` at all (before any own/team narrowing)."""
    if _role(user) in ALL_ACCESS_ROLES:
        return True
    mode, secs = _overrides(db, user.id)
    if mode == "none":
        return False
    return (not secs) or (section.lower() in secs)


def is_team_lead(db, user):
    """True if this user leads a SALES/RETENTION team — used to decide whether to show the
    'My team' toggle on list pages. Boss directive (Jul 21): the toggle is ONLY for sales/retention
    team leaders. Admin, customer_care, backoffice, finance, etc. must NOT see it (they see everything
    or have no team) — so gate to sales-side roles first, regardless of a fancy 'Manager/Director'
    title (that was letting admins like Nuha/Rahaf/Narmeen through)."""
    if _role(user) not in ("sales_agent", "sales_manager", "retention", "team_leader"):
        return False
    if _role(user) in ("sales_manager",):
        return True
    try:
        row = db.execute(text("SELECT COALESCE(title,''), (SELECT COUNT(*) FROM users c WHERE c.manager_id=:id) "
                              "FROM users WHERE id=:id"), {"id": user.id}).fetchone()
        title = (row[0] if row else "").lower()
        if "team leader" in title or "manager" in title or "director" in title:
            return True
        return bool(row and row[1])
    except Exception:
        db.rollback()
        return False


# Editing a lead's CORE INFORMATION (name / phone / email / country / city / KYC) is restricted to
# supervisory + ops roles. A plain sales_agent may still WORK their leads (change stage, log calls,
# add notes) but may NOT alter the lead's identity/contact data — desk security rule (ticket #191,
# Jul 2026). TIGHTENED Jul 21 (#241 + boss directive): ONLY the Admin team may edit lead/client
# information — no managers/supervisors/ops. (Nuha is role=admin, so covered.)
LEAD_INFO_EDIT_ROLES = {"super_admin", "admin", "director"}


def may_edit_lead_info(db, user) -> bool:
    """True if this user may edit a lead's identity/contact fields (not just its workflow).
    ADMIN TEAM ONLY (boss directive Jul 21, #241) — no supervisor/manager fallback: having a team
    does NOT grant information-editing rights. Sales/retention (any level) request changes from
    Admin (Nuha)."""
    return _role(user) in LEAD_INFO_EDIT_ROLES


def agent_filter(agent_ids, col="c.assigned_agent_id"):
    """SQL snippet + params to restrict `col` to the visible agent ids.
    Returns ('', {}) for full access. Uses a unique param name to avoid clashes."""
    if agent_ids is None:
        return "", {}
    if not agent_ids:
        return f" AND {col} = -1 ", {}
    return f" AND {col} = ANY(:rbac_agent_ids) ", {"rbac_agent_ids": agent_ids}


def can_see_agent(db, user, agent_id):
    """True if `user` is allowed to see data owned by `agent_id`."""
    ids = scope_agent_ids(db, user)
    return ids is None or (agent_id in ids)


def ensure_schema(db):
    """Add the per-user scope-override columns (idempotent). Safe to call at import."""
    try:
        db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS scope_mode VARCHAR(10)"))
        db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS scope_sections TEXT"))
        db.commit()
    except Exception:
        db.rollback()
