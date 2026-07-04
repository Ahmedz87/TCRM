"""Probe MT4 group config for per-symbol leverage (margin_divider) and margin call/stopout levels."""
import sys, ctypes
sys.path.insert(0, r"C:\broker-crm\backend")
from bridge_mt4 import load_dll, connect, get_manager, vcall, mem_free
from ctypes import (Structure, c_int, c_double, c_char, c_void_p, POINTER, byref, sizeof)

# Pack=1? MT4 structs are typically default-aligned (8-byte). Use default.

class ConGroupSec(Structure):
    _fields_ = [
        ("show", c_int), ("trade", c_int), ("execution", c_int),
        ("comm_base", c_double), ("comm_type", c_int), ("comm_lots", c_int),
        ("comm_agent", c_double), ("comm_agent_type", c_int),
        ("spread_diff", c_int),
        ("lot_min", c_int), ("lot_max", c_int), ("lot_step", c_int),
        ("ie_deviation", c_int), ("confirmation", c_int), ("trade_rights", c_int),
        ("ie_quick_mode", c_int), ("autocloseout_mode", c_int),
        ("comm_tax", c_double), ("comm_agent_lots", c_int),
        ("freemargin_mode", c_int), ("reserved", c_int * 3),
    ]

class ConGroupMargin(Structure):
    _fields_ = [
        ("symbol", c_char * 12),
        ("swap_long", c_double), ("swap_short", c_double),
        ("margin_divider", c_double),
        ("reserved", c_int * 7),
    ]

MAX_SEC_GROUPS = 32
MAX_SEC_GROPS_MARGIN = 128

# ConGroup — we only need fields up to secmargins_total + margin_call/stopout.
# Build the full struct prefix carefully.
class ConGroup(Structure):
    _fields_ = [
        ("group", c_char * 16),
        ("enable", c_int), ("timeout", c_int), ("otp_mode", c_int),
        ("company", c_char * 128), ("signature", c_char * 128),
        ("support_page", c_char * 128), ("smtp_server", c_char * 64),
        ("smtp_login", c_char * 32), ("smtp_password", c_char * 32),
        ("support_email", c_char * 64), ("templates", c_char * 32),
        ("copies", c_int), ("reports", c_int),
        ("default_leverage", c_int), ("default_deposit", c_double),
        ("maxsecurities", c_int),
        ("secgroups", ConGroupSec * MAX_SEC_GROUPS),
        ("secmargins", ConGroupMargin * MAX_SEC_GROPS_MARGIN),
        ("secmargins_total", c_int),
        ("currency", c_char * 12),
        ("credit", c_double),
        ("margin_call", c_int),
        ("margin_mode", c_int),
        ("margin_stopout", c_int),
        ("interestrate", c_double),
        ("use_swap", c_int),
        # ... rest not needed
    ]

print("ConGroupSec size:", sizeof(ConGroupSec))
print("ConGroupMargin size:", sizeof(ConGroupMargin))
print("ConGroup (partial) size:", sizeof(ConGroup))

load_dll(); connect()
man = get_manager()

# GroupsGet = slot 103
total = c_int(0)
ptr = vcall(man, 103, c_void_p, [POINTER(c_int)], byref(total))
print(f"\nGroupsGet returned: {total.value} groups, ptr={ptr}")

if ptr and total.value > 0:
    # We don't know the TRUE full ConGroup stride, so probe the first group only
    # by reading at ptr. If fields look sane, our struct prefix is aligned.
    g = ConGroup.from_address(ptr)
    name = g.group.decode("utf-8", errors="ignore").strip()
    print(f"\nFirst group: {name!r}")
    print(f"  default_leverage: {g.default_leverage}")
    print(f"  margin_call: {g.margin_call}")
    print(f"  margin_stopout: {g.margin_stopout}")
    print(f"  secmargins_total: {g.secmargins_total}")
    if 0 < g.secmargins_total <= 128:
        print("  Special securities (symbol -> margin_divider):")
        for i in range(min(g.secmargins_total, 20)):
            sm = g.secmargins[i]
            sym = sm.symbol.decode("utf-8", errors="ignore").strip()
            if sym:
                print(f"    {sym:12s} divider={sm.margin_divider}")
    mem_free(ptr)
