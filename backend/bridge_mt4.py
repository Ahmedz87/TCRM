"""
bridge_mt4.py â€” MT4 Manager API bridge to PostgreSQL broker_crm DB.

Architecture mirrors bridge.py (MT5). Connects via mtmanapi64.dll using
ctypes vtable calls (C++ virtual methods), which is the only way to drive
the MT4 Manager API from Python.

Run:  python bridge_mt4.py

Requires:
  - mtmanapi64.dll in the same directory (64-bit)
  - 64-bit Python
  - broker_crm PostgreSQL running

Sync schedule:
  Every 30s  : equity / margin update (MarginsGet)
  Every 5min : full sync (users + closed trades for transactions)
"""

import ctypes
import ctypes.wintypes as wt
import threading
from flask import Flask, jsonify

app = Flask(__name__)
from ctypes import (
    Structure, POINTER, WINFUNCTYPE,
    c_int, c_uint, c_double, c_float, c_char, c_char_p,
    c_void_p, c_short, c_longlong, byref, cast, sizeof,
)
import os, sys, time, logging, struct as pystruct
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bridge_mt4")

# â”€â”€ CONFIG â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
MT4_SERVER   = b"192.109.17.53:443"
MT4_LOGIN    = 1025
MT4_PASSWORD = b"Aqjf0pJ"
DLL_PATH     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mtmanapi64.dll")

# â”€â”€ VTABLE SLOT INDICES â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Counted from CManagerInterface declaration order in MT4ManagerAPI.h
V_QUERY_INTERFACE    = 0
V_ADDREF             = 1
V_RELEASE            = 2
V_MEM_FREE           = 3
V_ERROR_DESCRIPTION  = 4
V_WORKING_DIRECTORY  = 5
V_CONNECT            = 6
V_DISCONNECT         = 7
V_IS_CONNECTED       = 8
V_LOGIN              = 9
V_LOGIN_SECURED      = 10
V_KEYS_SEND          = 11
V_PING               = 12
# skip server admin (13-16) + config (17-65) + feeders (66-67) + charts (68-71)
# + performance (72) + backup (73-78)
V_ADM_USERS_REQUEST  = 79   # UserRecord* AdmUsersRequest(LPCSTR group, int* total)
V_ADM_TRADES_REQUEST = 80
V_ADM_BALANCE_FIX = 82   # TradeRecord* AdmTradesRequest(LPCSTR group, int open_only, int* total)
# skip balance/trade ops (81-84)
# symbols
V_SYMBOLS_REFRESH    = 85
V_SYMBOLS_GET_ALL    = 86   # ConSymbol* SymbolsGetAll(int* total)
# skip SymbolGet/SymbolInfoGet/SymbolAdd/SymbolHide (87-90)
# skip symbol cmds, users history (91-93, 94-96)
# skip LiveUpdateProfiles/HistoryOrders (97-99)
# skip ExternalCommand/PluginUpdate (100-101)
# pumping-mode methods (102+) â€” not used; we use direct Admin requests instead
V_PUMPING_SWITCH     = 102
V_GROUPS_GET         = 103  # ConGroup*  GroupsGet(int* total)
# skip GroupRecordGet/SymbolInfoUpdated
V_USERS_GET          = 106  # UserRecord* UsersGet(int* total)     [pumping-mode]
# skip UserRecordGet
V_ONLINE_GET         = 108  # OnlineRecord* OnlineGet(int* total)
# skip OnlineRecordGet
V_TRADES_GET         = 110  # TradeRecord*  TradesGet(int* total)  [pumping-mode]
# skip TradesGetBySymbol/Login/Market/TradeRecordGet/TradeClearRollback
V_MARGINS_GET        = 116  # MarginLevel*  MarginsGet(int* total)
# skip MarginLevelGet/RequestsGet/RequestInfoGet/PluginsGet/PluginParamGet
# skip MailLast/NewsGet/NewsTotal/NewsTopicGet/NewsBodyRequest/NewsBodyGet [dead in 64-bit]
V_SRV_GROUPS_GET     = 139  # int SymbolsGroupsGet(ConSymbolGroup* grp)  [32 entries]
V_CFG_REQUEST_SYM_GROUP = 22  # int CfgRequestSymbolGroup(ConSymbolGroup* cfg)

RET_OK = 0

# â”€â”€ STRUCTS â€” from MT4ManagerAPI.h (exact field order, packing as declared) â”€

class UserRecord(Structure):
    """No pragma pack on UserRecord â€” default alignment."""
    _fields_ = [
        ("login",                   c_int),
        ("group",                   c_char * 16),
        ("password",                c_char * 16),
        ("enable",                  c_int),
        ("enable_change_password",  c_int),
        ("enable_read_only",        c_int),
        ("enable_otp",              c_int),
        ("enable_flags",            c_int),
        ("enable_reserved",         c_int * 1),
        ("password_investor",       c_char * 16),
        ("password_phone",          c_char * 32),
        ("name",                    c_char * 128),
        ("country",                 c_char * 32),
        ("city",                    c_char * 32),
        ("state",                   c_char * 32),
        ("zipcode",                 c_char * 16),
        ("address",                 c_char * 96),
        ("lead_source",             c_char * 32),
        ("phone",                   c_char * 32),
        ("email",                   c_char * 48),
        ("comment",                 c_char * 64),
        ("id",                      c_char * 32),
        ("status",                  c_char * 16),
        ("regdate",                 c_int),
        ("lastdate",                c_int),
        ("leverage",                c_int),
        ("agent_account",           c_int),
        ("timestamp",               c_int),
        ("last_ip",                 c_int),
        ("balance",                 c_double),
        ("prevmonthbalance",        c_double),
        ("prevbalance",             c_double),
        ("credit",                  c_double),
        ("interestrate",            c_double),
        ("taxes",                   c_double),
        ("prevmonthequity",         c_double),
        ("prevequity",              c_double),
        ("reserved2",               c_double * 2),
        ("otp_secret",              c_char * 32),
        ("secure_reserved",         c_char * 240),
        ("send_reports",            c_int),
        ("mqid",                    c_uint),
        ("user_color",              c_uint),
        ("unused",                  c_char * 40),
        ("api_data",                c_char * 16),
    ]

class TradeRecord(Structure):
    """pragma pack(push,1) in header."""
    _pack_ = 1
    _fields_ = [
        ("order",               c_int),
        ("login",               c_int),
        ("symbol",              c_char * 12),
        ("digits",              c_int),
        ("cmd",                 c_int),
        ("volume",              c_int),
        ("open_time",           c_int),
        ("state",               c_int),
        ("open_price",          c_double),
        ("sl",                  c_double),
        ("tp",                  c_double),
        ("close_time",          c_int),
        ("gw_volume",           c_int),
        ("expiration",          c_int),
        ("reason",              c_char),
        ("conv_reserv",         c_char * 3),
        ("conv_rates",          c_double * 2),
        ("commission",          c_double),
        ("commission_agent",    c_double),
        ("storage",             c_double),
        ("close_price",         c_double),
        ("profit",              c_double),
        ("taxes",               c_double),
        ("magic",               c_int),
        ("comment",             c_char * 32),
        ("gw_order",            c_int),
        ("activation",          c_int),
        ("gw_open_price",       c_short),
        ("gw_close_price",      c_short),
        ("margin_rate",         c_double),
        ("timestamp",           c_int),
        ("api_data",            c_int * 4),
        ("next",                c_uint),   # TradeRecord* __ptr32 (32-bit ptr even in 64-bit build)
    ]

class OnlineRecord(Structure):
    """No pack override."""
    _fields_ = [
        ("counter",     c_int),
        ("reserved",    c_int),
        ("login",       c_int),
        ("ip",          c_uint),
        ("group",       c_char * 16),
    ]

class MarginLevel(Structure):
    """No pack override."""
    _fields_ = [
        ("login",           c_int),
        ("group",           c_char * 16),
        ("leverage",        c_int),
        ("updated",         c_int),
        ("balance",         c_double),
        ("equity",          c_double),
        ("volume",          c_int),
        ("margin",          c_double),
        ("margin_free",     c_double),
        ("margin_level",    c_double),
        ("margin_type",     c_int),
        ("level_type",      c_int),
    ]

class ConSymbolGroup(Structure):
    _fields_ = [
        ("name",        c_char * 16),
        ("description", c_char * 64),
    ]

# Trade commands
OP_BUY     = 0
OP_SELL    = 1
OP_BALANCE = 6
OP_CREDIT  = 7

# â”€â”€ VTABLE CALLER â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def vcall(obj, index, restype, argtypes, *args):
    """Call virtual method at vtable slot `index` on C++ object `obj`."""
    vtable = cast(obj, POINTER(c_void_p))
    funcs  = cast(vtable[0], POINTER(c_void_p))
    proto  = WINFUNCTYPE(restype, c_void_p, *argtypes)
    fn     = proto(funcs[index])
    return fn(obj, *args)

# â”€â”€ MANAGER SINGLETON â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_dll     = None
_manager = None

def load_dll():
    global _dll
    if _dll:
        return _dll
    if not os.path.exists(DLL_PATH):
        raise FileNotFoundError(f"mtmanapi64.dll not found at {DLL_PATH}")
    ws2 = ctypes.WinDLL("ws2_32.dll")
    ws2.WSAStartup(0x0202, byref((ctypes.c_byte * 512)()))
    _dll = ctypes.WinDLL(DLL_PATH)
    log.info("mtmanapi64.dll loaded")
    return _dll

def get_manager():
    global _manager, _dll
    if _manager:
        return _manager
    dll = load_dll()
    dll.MtManVersion.restype  = c_int
    dll.MtManVersion.argtypes = []
    ver = dll.MtManVersion()
    dll.MtManCreate.restype  = c_int
    dll.MtManCreate.argtypes = [c_int, POINTER(c_void_p)]
    man = c_void_p()
    dll.MtManCreate(ver, byref(man))
    if not man.value:
        raise RuntimeError("MtManCreate returned null manager")
    _manager = man
    log.info("MT4 manager instance created (ver=%d)", ver)
    return _manager

def connect():
    man = get_manager()
    rc = vcall(man, V_CONNECT, c_int, [c_char_p], MT4_SERVER)
    if rc != RET_OK:
        raise RuntimeError(f"Connect failed rc={rc}")
    rc = vcall(man, V_LOGIN, c_int, [c_int, c_char_p], MT4_LOGIN, MT4_PASSWORD)
    if rc != RET_OK:
        raise RuntimeError(f"Login failed rc={rc}")
    log.info("MT4 connected and logged in. IsConnected=%d",
             vcall(man, V_IS_CONNECTED, c_int, []))

def mem_free(ptr):
    if ptr:
        vcall(_manager, V_MEM_FREE, None, [c_void_p], ptr)

# â”€â”€ DATA FETCHERS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_all_users():
    """Fetch all user records via AdmUsersRequest('*')."""
    man   = get_manager()
    total = c_int(0)
    ptr   = vcall(man, V_ADM_USERS_REQUEST, c_void_p,
                  [c_char_p, POINTER(c_int)], b"*", byref(total))
    if not ptr or total.value <= 0:
        return []
    stride = sizeof(UserRecord)   # 1120 confirmed by probe_mt4_struct_size.py
    result = []
    for i in range(total.value):
        rec = UserRecord.from_address(ptr + i * stride)
        result.append({
            "login":    rec.login,
            "group":    rec.group.decode("utf-8", errors="ignore").strip(),
            "name":     rec.name.decode("utf-8", errors="ignore").strip(),
            "email":    rec.email.decode("utf-8", errors="ignore").strip(),
            "phone":    rec.phone.decode("utf-8", errors="ignore").strip(),
            "country":  rec.country.decode("utf-8", errors="ignore").strip(),
            "city":     rec.city.decode("utf-8", errors="ignore").strip(),
            "balance":  round(rec.balance, 2),
            "credit":   round(rec.credit, 2),
            "leverage": rec.leverage,
            "agent":    rec.agent_account,
            "mqid":     str(rec.mqid) if rec.mqid else "",
            "regdate":  rec.regdate,
        })
    mem_free(ptr)
    log.info("AdmUsersRequest: %d users", total.value)
    return result

def get_closed_trades(days: int = 3):
    """Fetch closed balance/credit operations via AdmTradesRequest."""
    man   = get_manager()
    total = c_int(0)
    ptr   = vcall(man, V_ADM_TRADES_REQUEST, c_void_p,
                  [c_char_p, c_int, POINTER(c_int)], b"*", 0, byref(total))
    if not ptr or total.value <= 0:
        return []
    stride  = sizeof(TradeRecord)
    cutoff  = int(time.time()) - days * 86400
    result  = []
    for i in range(total.value):
        rec = TradeRecord.from_address(ptr + i * stride)
        if rec.cmd not in (OP_BALANCE, OP_CREDIT):
            continue
        if rec.close_time < cutoff:
            continue
        result.append({
            "order":      rec.order,
            "login":      rec.login,
            "cmd":        rec.cmd,
            "profit":     rec.profit,
            "close_time": rec.close_time,
            "comment":    rec.comment.decode("utf-8", errors="ignore").strip(),
        })
    mem_free(ptr)
    log.info("AdmTradesRequest: %d total, %d balance/credit in last %dd",
             total.value, len(result), days)
    return result

def get_margins(logins: list = None):
    """
    Fetch real-time equity/margin.
    MarginsGet requires pumping mode (not used here).
    Instead use MarginLevelRequest per login â€” pass a list of logins to check,
    or omit to skip equity updates (balance comes from AdmUsersRequest anyway).
    """
    if not logins:
        return []
    man    = get_manager()
    result = []
    level  = MarginLevel()
    # vtable slot for MarginLevelRequest (line 1702 in header, count from interface start)
    # QueryInterface=0,AddRef=1,Release=2,MemFree=3,ErrorDesc=4,WorkDir=5,
    # Connect=6,Disconnect=7,IsConnected=8,Login=9,LoginSecured=10,KeysSend=11,
    # Ping=12,PasswordChange=13,ManagerRights=14,
    # SrvRestart=15,SrvChartsSync=16,SrvLiveUpdateStart=17,SrvFeedsRestart=18,
    # CfgRequestCommon=19..CfgRequestPlugin=32, CfgUpdateCommon=33..CfgUpdatePlugin=46,
    # CfgDeleteAccess=47..CfgDeleteSync=55, CfgShiftAccess=56..CfgShiftPlugin=65,
    # SrvFeeders=66,SrvFeederLog=67, ChartRequestObs=68..ChartDeleteObs=71,
    # PerformanceRequest=72, BackupInfoUsers=73,BackupInfoOrders=74,
    # BackupRequestUsers=75,BackupRequestOrders=76,BackupRestoreUsers=77,BackupRestoreOrders=78,
    # AdmUsersRequest=79,AdmTradesRequest=80,AdmBalanceCheckObs=81,AdmBalanceFix=82,
    # AdmTradesDelete=83,AdmTradeRecordModify=84,
    # SymbolsRefresh=85,SymbolsGetAll=86,SymbolGet=87,SymbolInfoGet=88,SymbolAdd=89,SymbolHide=90,
    # [symbol cmds 91-93], [history 94-96], [liveupdate 97], [history orders 98-99],
    # ExternalCommand=100, PluginUpdate=101,
    # PumpingSwitch=102,GroupsGet=103,GroupRecordGet=104,SymbolInfoUpdated=105,
    # UsersGet=106,UserRecordGet=107,OnlineGet=108,OnlineRecordGet=109,
    # TradesGet=110,TradesGetBySymbol=111,TradesGetByLogin=112,TradesGetByMarket=113,
    # TradeRecordGet=114,TradeClearRollback=115,
    # MarginsGet=116,MarginLevelGet=117,RequestsGet=118,RequestInfoGet=119,
    # PluginsGet=120,PluginParamGet=121,MailLast=122,
    # NewsGet=123,NewsTotal=124,NewsTopicGet=125,NewsBodyRequest=126,NewsBodyGet=127,
    # DealerSwitch=128,DealerRequestGet=129,DealerSend=130,DealerReject=131,DealerReset=132,
    # TickInfoLast=133,SymbolsGroupsGet=134,ServerTime=135,MailsRequest=136,
    # SummaryGetAll=137..ExposureValueGet=143,
    # MarginLevelRequest=144
    V_MARGIN_LEVEL_REQUEST = 144
    for login in logins:
        try:
            rc = vcall(man, V_MARGIN_LEVEL_REQUEST, c_int,
                       [c_int, POINTER(MarginLevel)], login, byref(level))
            if rc == RET_OK and level.login > 0:
                result.append({
                    "login":        level.login,
                    "equity":       round(level.equity, 2),
                    "balance":      round(level.balance, 2),
                    "margin":       round(level.margin, 2),
                    "margin_free":  round(level.margin_free, 2),
                    "margin_level": round(level.margin_level, 2),
                })
        except Exception:
            pass
    log.info("MarginLevelRequest: %d/%d accounts updated", len(result), len(logins))
    return result

def get_symbol_groups():
    """Fetch 32 symbol group name slots (CfgRequestSymbolGroup)."""
    man = get_manager()
    grp = (ConSymbolGroup * 32)()
    rc  = vcall(man, V_CFG_REQUEST_SYM_GROUP, c_int,
                [POINTER(ConSymbolGroup)], grp)
    if rc != RET_OK:
        log.warning("CfgRequestSymbolGroup rc=%d", rc)
        return {}
    groups = {}
    for i, g in enumerate(grp):
        name = g.name.decode("utf-8", errors="ignore").strip()
        if name:
            groups[i] = name
    return groups  # {index: group_name}

def get_all_symbols():
    """Fetch all symbol configs and return list of dicts with name/group/currency."""
    man   = get_manager()
    total = c_int(0)
    ptr   = vcall(man, V_SYMBOLS_GET_ALL, c_void_p, [POINTER(c_int)], byref(total))
    if not ptr or total.value <= 0:
        return []
    # ConSymbol is large; parse manually using struct offsets from the header
    # Offsets: symbol @0 (12 bytes), description @12 (64), currency @88 (12), type @100 (int)
    from ctypes import string_at
    groups = get_symbol_groups()
    results = []
    sym_size = 1936  # sizeof(ConSymbol) from header field count â€” see below
    for i in range(total.value):
        base = ptr + i * sym_size
        symbol   = string_at(base + 0,   12).split(b"\x00")[0].decode("utf-8", errors="ignore")
        descr    = string_at(base + 12,  64).split(b"\x00")[0].decode("utf-8", errors="ignore")
        currency = string_at(base + 88,  12).split(b"\x00")[0].decode("utf-8", errors="ignore")
        type_val = pystruct.unpack_from("<i", (ctypes.c_byte * 4).from_address(base + 100))[0]
        group_name = groups.get(type_val, "")
        if symbol:
            results.append({"symbol": symbol, "description": descr,
                             "currency": currency, "type": type_val,
                             "group_name": group_name})
    mem_free(ptr)
    log.info("SymbolsGetAll: %d symbols", len(results))
    return results

# â”€â”€ DB WRITES â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_db():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from database import SessionLocal
    return SessionLocal()

def save_mt4_clients(users: list):
    from sqlalchemy import text
    db = get_db()
    try:
        count = 0
        for u in users:
            login = u["login"]
            if login <= 0:
                continue
            db.execute(text("""
                INSERT INTO clients (login, name, email, phone, country, city,
                    balance, credit, leverage, group_name, agent, mqid,
                    reg_date, platform, created_at, mt_last_seen)
                VALUES (:login,:name,:email,:phone,:country,:city,
                    :balance,:credit,:leverage,:group_name,:agent,:mqid,
                    :reg_date,'MT4',NOW(),NOW())
                ON CONFLICT (login) DO UPDATE SET
                    name=EXCLUDED.name, email=EXCLUDED.email,
                    phone=EXCLUDED.phone, balance=EXCLUDED.balance,
                    credit=EXCLUDED.credit, leverage=EXCLUDED.leverage,
                    group_name=EXCLUDED.group_name, agent=EXCLUDED.agent,
                    mqid=EXCLUDED.mqid, platform='MT4',
                    mt_last_seen=NOW()   -- archive detector: stamp every account present in MT4
            """), {
                "login":      login,
                "name":       u["name"],
                "email":      u["email"],
                "phone":      u["phone"],
                "country":    u["country"],
                "city":       u["city"],
                "balance":    u["balance"],
                "credit":     u["credit"],
                "leverage":   u["leverage"],
                "group_name": u["group"],
                "agent":      u["agent"],
                "mqid":       u["mqid"],
                "reg_date":   datetime.fromtimestamp(u["regdate"]).strftime("%Y-%m-%d") if u["regdate"] else None,
            })
            count += 1
            if count % 500 == 0:
                db.commit()
                log.info("MT4 clients: %d saved...", count)
        db.commit()
        log.info("MT4: %d clients saved", count)
    except Exception as e:
        db.rollback()
        log.error("save_mt4_clients: %s", e)
    finally:
        db.close()

def save_mt4_transactions(trades: list):
    from sqlalchemy import text
    db = get_db()
    try:
        count = 0
        for t in trades:
            comment = t["comment"]
            profit  = t["profit"]
            cmd     = t["cmd"]

            if cmd == OP_CREDIT:
                tx_type = "credit_in" if profit > 0 else "credit_out"
            elif "transfer" in comment.lower():
                tx_type = "internal_transfer"
            elif "bonus" in comment.lower():
                tx_type = "bonus_deposit" if profit > 0 else "bonus_withdrawal"
            elif profit > 0:
                tx_type = "deposit"
            elif profit < 0:
                tx_type = "withdrawal"
            else:
                continue

            method = ""
            if " - " in comment:
                parts = comment.split(" - ")
                if len(parts) >= 2:
                    method = parts[1].strip()

            tx_date = datetime.fromtimestamp(t["close_time"]) if t["close_time"] else None

            db.execute(text("""
                INSERT INTO transactions (deal_id, login, tx_type, amount, method,
                    status, tx_date, notes, platform, created_at)
                VALUES (:deal_id,:login,:tx_type,:amount,:method,
                    'approved',:tx_date,:notes,'MT4',NOW())
                ON CONFLICT (deal_id) DO NOTHING
            """), {
                "deal_id": t["order"],
                "login":   t["login"],
                "tx_type": tx_type,
                "amount":  abs(profit),
                "method":  method,
                "tx_date": tx_date,
                "notes":   comment,
            })
            count += 1
            if count % 2000 == 0:
                db.commit()
                log.info("MT4 transactions: %d saved...", count)
        db.commit()
        log.info("MT4: %d transactions saved", count)
    except Exception as e:
        db.rollback()
        log.error("save_mt4_transactions: %s", e)
    finally:
        db.close()

def update_mt4_equity(margins: list):
    from sqlalchemy import text
    db = get_db()
    try:
        count = 0
        for m in margins:
            db.execute(text("""
                UPDATE clients SET equity=:eq, margin_level=:ml
                WHERE login=:login AND platform='MT4'
            """), {"eq": m["equity"], "ml": m["margin_level"], "login": m["login"]})
            db.execute(text("""
                UPDATE trading_accounts SET equity=:eq, margin_level=:ml,
                    balance=:bal, free_margin=:fm
                WHERE login=:login
            """), {"eq": m["equity"], "ml": m["margin_level"],
                   "bal": m["balance"], "fm": m["margin_free"],
                   "login": m["login"]})
            count += 1
        db.commit()
        log.info("MT4: %d accounts equity updated", count)
    except Exception as e:
        db.rollback()
        log.error("update_mt4_equity: %s", e)
    finally:
        db.close()

def sync_symbols():
    """Sync MT4 symbols (name/group/currency) into the Symbol table."""
    try:
        syms = get_all_symbols()
    except Exception as e:
        log.warning("sync_symbols skipped: %s", e)
        return
    from sqlalchemy import text
    db = get_db()
    try:
        for s in syms:
            db.execute(text("""
                INSERT INTO symbols (name, symbol_group, currency_profit, description, platform)
                VALUES (:name,:grp,:cur,:desc,'MT4')
                ON CONFLICT (name) DO UPDATE SET
                    symbol_group=EXCLUDED.symbol_group,
                    currency_profit=EXCLUDED.currency_profit,
                    description=EXCLUDED.description
            """), {"name": s["symbol"], "grp": s["group_name"],
                   "cur": s["currency"], "desc": s["description"]})
        db.commit()
        log.info("MT4 symbols synced: %d", len(syms))
    except Exception as e:
        db.rollback()
        log.warning("sync_symbols DB error: %s (symbols table may need platform column)", e)
    finally:
        db.close()

def get_trade_history(days: int = 3):
    """Fetch actual MT4 trade history (buy/sell deals) via AdmTradesRequest."""
    man   = get_manager()
    total = c_int(0)
    ptr   = vcall(man, V_ADM_TRADES_REQUEST, c_void_p,
                  [c_char_p, c_int, POINTER(c_int)], b"*", 0, byref(total))
    if not ptr or total.value <= 0:
        return []
    stride = sizeof(TradeRecord)
    cutoff = int(time.time()) - days * 86400
    result = []
    for i in range(total.value):
        rec = TradeRecord.from_address(ptr + i * stride)
        if rec.cmd not in (0, 1, 2, 3, 4, 5):
            continue
        if rec.close_time <= 0 or rec.close_time < cutoff:
            continue
        symbol  = rec.symbol.decode("utf-8", errors="ignore").strip()
        comment = rec.comment.decode("utf-8", errors="ignore").strip()
        result.append({
            "order":       rec.order,
            "login":       rec.login,
            "symbol":      symbol,
            "cmd":         rec.cmd,
            "volume":      rec.volume / 100.0,
            "open_price":  rec.open_price,
            "close_price": rec.close_price,
            "open_time":   rec.open_time,
            "close_time":  rec.close_time,
            "profit":      rec.profit,
            "commission":  rec.commission,
            "swap":        rec.storage,
            "comment":     comment,
        })
    mem_free(ptr)
    log.info("get_trade_history: %d total, %d trades in last %dd",
             total.value, len(result), days)
    return result


def save_mt4_deals(trades: list):
    """Save MT4 actual trades into the deals table."""
    from sqlalchemy import text
    db = get_db()
    import schema_guard
    schema_guard.ensure_column(db, "deals", "platform", "VARCHAR(10) DEFAULT 'MT5'")  # no-op once present, never locks
    try:
        count = 0
        for t in trades:
            close_dt   = datetime.fromtimestamp(t["close_time"]) if t["close_time"] else None
            deal_date  = close_dt.strftime("%Y-%m-%d") if close_dt else None
            deal_month = close_dt.strftime("%Y-%m")    if close_dt else None
            deal_year  = close_dt.year                 if close_dt else None
            direction  = "buy" if t["cmd"] in (0, 2, 4) else "sell"
            row = db.execute(text(
                "SELECT client_id FROM trading_accounts WHERE login=:l AND platform='MT4' LIMIT 1"
            ), {"l": t["login"]}).fetchone()
            client_id = row[0] if row else None
            db.execute(text("""
                INSERT INTO deals (
                    deal_id, login, client_id, symbol,
                    action, deal_type, direction,
                    volume, price, profit, commission, swap,
                    comment, deal_time, deal_date, deal_month, deal_year,
                    balance_after, platform, created_at
                ) VALUES (
                    :deal_id, :login, :client_id, :symbol,
                    :action, 'trade', :direction,
                    :volume, :price, :profit, :commission, :swap,
                    :comment, :deal_time, :deal_date, :deal_month, :deal_year,
                    0, 'MT4', NOW()
                )
                ON CONFLICT (deal_id) DO NOTHING
            """), {
                "deal_id":    t["order"],
                "login":      t["login"],
                "client_id":  client_id,
                "symbol":     t["symbol"],
                "action":     t["cmd"],
                "direction":  direction,
                "volume":     t["volume"],
                "price":      t["close_price"],
                "profit":     t["profit"],
                "commission": t["commission"],
                "swap":       t["swap"],
                "comment":    t["comment"],
                "deal_time":  t["close_time"],
                "deal_date":  deal_date,
                "deal_month": deal_month,
                "deal_year":  deal_year,
            })
            count += 1
            if count % 2000 == 0:
                db.commit()
                log.info("MT4 deals: %d saved...", count)
        db.commit()
        log.info("MT4: %d deals saved", count)
    except Exception as e:
        db.rollback()
        log.error("save_mt4_deals: %s", e)
    finally:
        db.close()


def get_online_users():
    man   = get_manager()
    total = c_int(0)
    ptr   = vcall(man, V_ONLINE_GET, c_void_p, [POINTER(c_int)], byref(total))
    if not ptr or total.value <= 0:
        return []
    stride = sizeof(OnlineRecord)
    result = []
    for i in range(total.value):
        rec   = OnlineRecord.from_address(ptr + i * stride)
        ip_int = rec.ip
        ip_str = f"{ip_int & 0xFF}.{(ip_int>>8)&0xFF}.{(ip_int>>16)&0xFF}.{(ip_int>>24)&0xFF}"
        result.append({
            "login": rec.login,
            "ip":    ip_str,
            "group": rec.group.decode("utf-8", errors="ignore").strip(),
        })
    mem_free(ptr)
    log.info("OnlineGet: %d users online", len(result))
    return result


def save_online_identifiers(online: list):
    """Upsert current online IPs into account_identifiers."""
    from sqlalchemy import text
    from datetime import datetime, timezone
    if not online:
        return
    db  = get_db()
    now = datetime.now(timezone.utc)
    try:
        for o in online:
            if not o["ip"] or o["ip"].startswith("0."):
                continue
            db.execute(text("""
                INSERT INTO account_identifiers
                    (login, identifier_type, identifier_value, first_seen, last_seen, seen_count)
                VALUES (:login, 'ip', :ip, :now, :now, 1)
                ON CONFLICT (login, identifier_type, identifier_value)
                DO UPDATE SET
                    last_seen  = EXCLUDED.last_seen,
                    seen_count = account_identifiers.seen_count + 1
            """), {"login": o["login"], "ip": o["ip"], "now": now})
        db.commit()
        log.info("Online identifiers: %d IPs upserted", len(online))
    except Exception as e:
        db.rollback()
        log.error("save_online_identifiers: %s", e)
    finally:
        db.close()
def get_open_trades():
    """Fetch all currently open MT4 trades."""
    man   = get_manager()
    total = c_int(0)
    ptr   = vcall(man, V_ADM_TRADES_REQUEST, c_void_p,
                  [c_char_p, c_int, POINTER(c_int)], b"*", 1, byref(total))
    if not ptr or total.value <= 0:
        return []
    stride = sizeof(TradeRecord)
    result = []
    for i in range(total.value):
        rec    = TradeRecord.from_address(ptr + i * stride)
        if rec.cmd not in (0, 1, 2, 3, 4, 5):
            continue
        symbol  = rec.symbol.decode("utf-8", errors="ignore").strip()
        comment = rec.comment.decode("utf-8", errors="ignore").strip()
        result.append({
            "order":      rec.order,
            "login":      rec.login,
            "symbol":     symbol,
            "cmd":        rec.cmd,
            "volume":     rec.volume / 100.0,
            "open_price": rec.open_price,
            "open_time":  rec.open_time,
            "profit":     rec.profit,
            "swap":       rec.storage,
            "commission": rec.commission,
            "comment":    comment,
        })
    mem_free(ptr)
    log.info("AdmTradesRequest open: %d trades", len(result))
    return result


def save_open_trades(trades: list):
    """Upsert currently open MT4 trades into a tracking table."""
    from sqlalchemy import text
    db = get_db()
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS mt4_open_trades (
                order_id    INTEGER PRIMARY KEY,
                login       INTEGER,
                symbol      VARCHAR(32),
                cmd         INTEGER,
                direction   VARCHAR(8),
                volume      DOUBLE PRECISION,
                open_price  DOUBLE PRECISION,
                open_time   INTEGER,
                profit      DOUBLE PRECISION,
                swap        DOUBLE PRECISION,
                commission  DOUBLE PRECISION,
                comment     VARCHAR(64),
                updated_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        db.commit()

        # Clear old open trades and replace with current snapshot
        db.execute(text("DELETE FROM mt4_open_trades"))
        count = 0
        for t in trades:
            direction = "buy" if t["cmd"] in (0, 2, 4) else "sell"
            db.execute(text("""
                INSERT INTO mt4_open_trades
                    (order_id, login, symbol, cmd, direction, volume,
                     open_price, open_time, profit, swap, commission, comment, updated_at)
                VALUES
                    (:order_id, :login, :symbol, :cmd, :direction, :volume,
                     :open_price, :open_time, :profit, :swap, :commission, :comment, NOW())
                ON CONFLICT (order_id) DO UPDATE SET
                    profit=EXCLUDED.profit, swap=EXCLUDED.swap,
                    updated_at=NOW()
            """), {
                "order_id":   t["order"],
                "login":      t["login"],
                "symbol":     t["symbol"],
                "cmd":        t["cmd"],
                "direction":  direction,
                "volume":     t["volume"],
                "open_price": t["open_price"],
                "open_time":  t["open_time"],
                "profit":     t["profit"],
                "swap":       t["swap"],
                "commission": t["commission"],
                "comment":    t["comment"],
            })
            count += 1
        db.commit()
        log.info("MT4 open trades saved: %d", count)
    except Exception as e:
        db.rollback()
        log.error("save_open_trades: %s", e)
    finally:
        db.close()
def sync_trade_journal(days: int = 3):
    """Fetch closed trades from MT4 journal (LOG_TYPE_TRADES) and save to deals.
    This is the WORKING method — AdmTradesRequest does not return closed trades
    on this server, but the journal does.
    """
    import re
    from ctypes import string_at
    man = get_manager()
    SERVERLOG_SIZE = 796
    OFFSET_TIME = 4
    OFFSET_MSG  = 284
    RE_CLOSE = re.compile(
        r"'(\d+)':\s*close order #(\d+)\s*\((buy|sell)\s+([\d.]+)\s+(\S+)\s+at\s+([\d.]+)\)\s+at\s+([\d.]+)"
    )
    from_time = int(time.time()) - days * 86400
    to_time   = int(time.time())
    total = c_int(0)
    ptr = vcall(man, 96, c_void_p,
                [c_int, c_int, c_int, c_char_p, POINTER(c_int)],
                2, from_time, to_time, b"", byref(total))
    if not ptr or total.value <= 0:
        return []
    cmd_map = {"buy": 0, "sell": 1}
    trades = []
    for i in range(total.value):
        off = ptr + i * SERVERLOG_SIZE + OFFSET_MSG
        msg = string_at(off, 512).split(b"\x00")[0].decode("utf-8", errors="ignore")
        m = RE_CLOSE.search(msg)
        if not m:
            continue
        toff = ptr + i * SERVERLOG_SIZE + OFFSET_TIME
        tstr = string_at(toff, 24).split(b"\x00")[0].decode("utf-8", errors="ignore").strip()
        try:
            dt = datetime.strptime(tstr[:19], "%Y.%m.%d %H:%M:%S")
        except Exception:
            dt = None
        trades.append({
            "order":       int(m.group(2)),
            "login":       int(m.group(1)),
            "symbol":      m.group(5),
            "cmd":         cmd_map[m.group(3)],
            "direction":   m.group(3),
            "volume":      float(m.group(4)),
            "open_price":  float(m.group(6)),
            "close_price": float(m.group(7)),
            "dt":          dt,
        })
    mem_free(ptr)
    log.info("sync_trade_journal: %d records, %d closed trades in last %dd",
             total.value, len(trades), days)
    return trades


def save_journal_deals(trades: list):
    """Save journal-parsed closed trades into deals table."""
    from sqlalchemy import text
    if not trades:
        return
    db = get_db()
    import schema_guard
    schema_guard.ensure_column(db, "deals", "platform", "VARCHAR(10) DEFAULT 'MT5'")  # no-op once present, never locks
    try:
        count = 0
        for t in trades:
            dt = t["dt"]
            deal_time  = int(dt.timestamp()) if dt else None
            deal_date  = dt.strftime("%Y-%m-%d") if dt else None
            deal_month = dt.strftime("%Y-%m")    if dt else None
            deal_year  = dt.year                 if dt else None
            row = db.execute(text(
                "SELECT client_id, balance FROM trading_accounts WHERE login=:l AND platform='MT4' LIMIT 1"
            ), {"l": t["login"]}).fetchone()
            client_id = row[0] if row else None
            bal = float(row[1]) if row and row[1] is not None else 0.0   # account balance -> credit detection
            db.execute(text("""
                INSERT INTO deals (
                    deal_id, login, client_id, symbol, action, deal_type, direction,
                    volume, price, profit, commission, swap, comment,
                    deal_time, deal_date, deal_month, deal_year, balance_after, platform, created_at
                ) VALUES (
                    :deal_id, :login, :client_id, :symbol, :action, 'trade', :direction,
                    :volume, :price, 0, 0, 0, '',
                    :deal_time, :deal_date, :deal_month, :deal_year, :bal, 'MT4', NOW()
                )
                ON CONFLICT (deal_id) DO NOTHING
            """), {
                "deal_id":    t["order"],
                "login":      t["login"],
                "client_id":  client_id,
                "bal":        bal,
                "symbol":     t["symbol"],
                "action":     t["cmd"],
                "direction":  t["direction"],
                "volume":     t["volume"],
                "price":      t["close_price"],
                "deal_time":  deal_time,
                "deal_date":  deal_date,
                "deal_month": deal_month,
                "deal_year":  deal_year,
            })
            count += 1
            if count % 2000 == 0:
                db.commit()
        db.commit()
        log.info("MT4 journal deals saved: %d", count)
    except Exception as e:
        db.rollback()
        log.error("save_journal_deals: %s", e)
    finally:
        db.close()
def sync_login_identifiers(days: int = 1):
    """Parse journal login entries for IP + CID and upsert to account_identifiers.
    Runs in the 5-min cycle to keep network identifiers fresh.
    """
    import re
    from ctypes import string_at
    from sqlalchemy import text
    man = get_manager()
    SERVERLOG_SIZE = 796
    OFFSET_IP  = 28
    OFFSET_MSG = 284
    RE_LOGIN = re.compile(r"'(\d+)':\s*login")
    RE_CID   = re.compile(r"\bcid:\s*([0-9a-fA-F]{16,})")
    from_time = int(time.time()) - days * 86400
    to_time   = int(time.time())
    total = c_int(0)
    ptr = vcall(man, 96, c_void_p,
                [c_int, c_int, c_int, c_char_p, POINTER(c_int)],
                1, from_time, to_time, b"", byref(total))
    if not ptr or total.value <= 0:
        return
    login_ips  = {}
    login_cids = {}
    for i in range(total.value):
        off_ip  = ptr + i * SERVERLOG_SIZE + OFFSET_IP
        off_msg = ptr + i * SERVERLOG_SIZE + OFFSET_MSG
        ip  = string_at(off_ip, 256).split(b"\x00")[0].decode("utf-8", errors="ignore").strip()
        msg = string_at(off_msg, 512).split(b"\x00")[0].decode("utf-8", errors="ignore")
        m = RE_LOGIN.search(msg)
        if not m:
            continue
        login = int(m.group(1))
        if login <= 0:
            continue
        if ip:
            login_ips.setdefault(login, set()).add(ip)
        mc = RE_CID.search(msg)
        if mc:
            login_cids.setdefault(login, set()).add(mc.group(1).lower())
    mem_free(ptr)

    db = get_db()
    now = datetime.now(timezone.utc)
    try:
        for login, ips in login_ips.items():
            for ip in ips:
                if not ip or ip.startswith("0."):
                    continue
                db.execute(text("""
                    INSERT INTO account_identifiers (login, identifier_type, identifier_value, first_seen, last_seen, seen_count)
                    VALUES (:login, 'ip', :v, :now, :now, 1)
                    ON CONFLICT (login, identifier_type, identifier_value)
                    DO UPDATE SET last_seen=:now, seen_count=account_identifiers.seen_count+1
                """), {"login": login, "v": ip, "now": now})
        for login, cids in login_cids.items():
            for cid in cids:
                db.execute(text("""
                    INSERT INTO account_identifiers (login, identifier_type, identifier_value, first_seen, last_seen, seen_count)
                    VALUES (:login, 'cid', :v, :now, :now, 1)
                    ON CONFLICT (login, identifier_type, identifier_value)
                    DO UPDATE SET last_seen=:now, seen_count=account_identifiers.seen_count+1
                """), {"login": login, "v": cid, "now": now})
        db.commit()
        log.info("MT4 identifiers: %d logins with IP, %d with CID", len(login_ips), len(login_cids))
    except Exception as e:
        db.rollback()
        log.error("sync_login_identifiers: %s", e)
    finally:
        db.close()
def update_equity_from_trades(open_trades: list):
    """Equity = Balance + Credit + sum(open trade floating PnL). Every 30s."""
    from sqlalchemy import text
    if not open_trades:
        return
    pnl_by_login = {}
    for t in open_trades:
        login = t["login"]
        floating = t.get("profit", 0) + t.get("swap", 0) + t.get("commission", 0)
        pnl_by_login[login] = pnl_by_login.get(login, 0) + floating
    db = get_db()
    try:
        count = 0
        for login, floating_pnl in pnl_by_login.items():
            row = db.execute(text(
                "SELECT balance, credit FROM trading_accounts WHERE login=:l AND platform='MT4'"
            ), {"l": login}).fetchone()
            if not row:
                continue
            balance = float(row[0] or 0)
            credit  = float(row[1] or 0)
            equity  = balance + credit + floating_pnl
            db.execute(text("""
                UPDATE trading_accounts SET equity=:eq, free_margin=:fm, updated_at=NOW()
                WHERE login=:l AND platform='MT4'
            """), {"eq": equity, "fm": floating_pnl, "l": login})
            db.execute(text("UPDATE clients SET equity=:eq WHERE login=:l"),
                       {"eq": equity, "l": login})
            count += 1
        db.commit()
        log.info("MT4 equity updated for %d accounts (from open trades)", count)
    except Exception as e:
        db.rollback()
        log.error("update_equity_from_trades: %s", e)
    finally:
        db.close()
def _contract_size(symbol):
    s = symbol.upper().split(".")[0].strip()
    if s.startswith("XAU"): return 100.0
    if s.startswith("XAG"): return 5000.0
    if s.startswith("XPT") or s.startswith("XPD"): return 100.0
    if s in ("USOIL","UKOIL","WTI","BRENT","XBRUSD","XTIUSD"): return 1000.0
    crypto = ("BTC","ETH","XRP","LTC","BCH","XMR","XTZ","DSH","BSV","ADA","DOT","EOS","XLM")
    if any(s.startswith(c) for c in crypto): return 1.0
    fx = ("USD","EUR","GBP","JPY","CHF","CAD","AUD","NZD","SEK","NOK","DKK","TRY","ZAR","MXN","SGD","HKD","PLN","CNH","CZK","HUF")
    if len(s)==6 and s[:3] in fx and s[3:] in fx: return 100000.0
    indices = ("US30","NAS100","SPX500","US500","JP225","GER40","GER30","UK100","SPAIN35","FRA40","AUS200","HK50","EU50","NAS","DAX")
    if any(s.startswith(idx) for idx in indices): return 1.0
    return 1.0


def update_margin_levels(open_trades):
    from sqlalchemy import text
    if not open_trades:
        return
    agg = {}
    for t in open_trades:
        login = t["login"]
        a = agg.setdefault(login, {"pnl": 0.0, "margin_base": 0.0})
        a["pnl"] += t.get("profit",0) + t.get("swap",0) + t.get("commission",0)
        cs = _contract_size(t["symbol"])
        a["margin_base"] += t["volume"] * cs * t["open_price"]
    db = get_db()
    try:
        count=0; margin_calls=0
        for login, a in agg.items():
            row = db.execute(text(
                "SELECT balance, credit, leverage FROM trading_accounts WHERE login=:l AND platform='MT4'"
            ), {"l": login}).fetchone()
            if not row:
                continue
            balance=float(row[0] or 0); credit=float(row[1] or 0)
            leverage=float(row[2] or 100) or 100
            equity = balance + credit + a["pnl"]
            used_margin = a["margin_base"] / leverage
            margin_level = (equity/used_margin*100.0) if used_margin>0 else 0.0
            is_mc = used_margin>0 and margin_level<100.0
            db.execute(text("""
                UPDATE trading_accounts SET equity=:eq, margin_level=:ml, free_margin=:fm, updated_at=NOW()
                WHERE login=:l AND platform='MT4'
            """), {"eq":equity,"ml":margin_level,"fm":equity-used_margin,"l":login})
            db.execute(text("UPDATE clients SET equity=:eq, margin_level=:ml WHERE login=:l"),
                       {"eq":equity,"ml":margin_level,"l":login})
            count+=1
            if is_mc: margin_calls+=1
        db.commit()
        log.info("MT4 margin: %d accounts updated, %d in margin call", count, margin_calls)
    except Exception as e:
        db.rollback()
        log.error("update_margin_levels: %s", e)
    finally:
        db.close()
        db.close()
# â”€â”€ SYNC LOOP â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def sync_loop():
    log.info("=" * 50)
    log.info("MT4 Bridge starting")
    log.info("Server: %s  Login: %d", MT4_SERVER.decode(), MT4_LOGIN)
    log.info("=" * 50)

    while True:
        try:
            load_dll()
            connect()
            break
        except Exception as e:
            log.error("Startup error: %s â€” retrying in 30s", e)
            time.sleep(30)

    cycle = 0
    while True:
        next_run = time.time() + 30
        cycle += 1
        try:
            if not vcall(_manager, V_IS_CONNECTED, c_int, []):
                log.warning("MT4 disconnected â€” reconnecting")
                connect()

            # Full sync every 10 cycles (5 min)
            if cycle == 1 or cycle % 10 == 0:
                log.info("MT4 full sync start (cycle %d)", cycle)
                users  = get_all_users()
                if users:
                    save_mt4_clients(users)
                trades = get_closed_trades(days=3)
                if trades:
                    save_mt4_transactions(trades)
                deal_trades = sync_trade_journal(days=3)
                if deal_trades:
                    save_journal_deals(deal_trades)
                if cycle % 100 == 0:   # symbols every ~50 min
                    sync_symbols()
                log.info("MT4 full sync done")

            # Open trades snapshot every 30s
            open_trades = get_open_trades()
            if open_trades:
                save_open_trades(open_trades)
                update_margin_levels(open_trades)

            # Online users — update IPs every 30s
            online = get_online_users()
            if online:
                save_online_identifiers(online)

            # Equity every 30s â€” sample active accounts only (first 100 for speed)
            sample_logins = [u["login"] for u in get_all_users()[:100]]
            margins = get_margins(sample_logins)
            if margins:
                update_mt4_equity(margins)

        except Exception as e:
            log.error("MT4 sync error: %s", e)
            try:
                connect()
            except Exception:
                pass

        sleep_time = next_run - time.time()
        if sleep_time > 0:
            time.sleep(sleep_time)



# ─────────── HTTP ENDPOINTS (read-only for now) ───────────
def _get_user_record(login):
    """Read one user's balance/credit via AdmUsersRequest, filtered to login."""
    for u in get_all_users():
        if u["login"] == login:
            return u
    return None

@app.route("/mt4/inspect/<int:login>", methods=["GET"])
def mt4_inspect(login):
    """Read-only: balance, credit, open positions, floating PnL for a login."""
    try:
        u = _get_user_record(login)
        if not u:
            return jsonify({"login": login, "error": "user not found"}), 404
        bal = u["balance"]
        cred = u["credit"]
        # Open trades for this login + floating PnL
        try:
            all_trades = get_open_trades()
        except Exception:
            all_trades = []
        mine = [t for t in all_trades if t.get("login") == login]
        # Only count market trades (cmd 0=buy,1=sell) as positions, not balance ops
        positions = [t for t in mine if t.get("cmd") in (0, 1)]
        floating = sum(float(t.get("profit", 0)) for t in positions)
        return jsonify({
            "login": login, "balance": bal, "credit": cred,
            "positions": len(positions), "floating_pnl": round(floating, 2)
        })
    except Exception as e:
        return jsonify({"login": login, "error": str(e)}), 500


@app.route("/mt4/cover/<int:login>", methods=["POST"])
def mt4_cover(login):
    """Cover negative balance. DRY-RUN by default. Pass ?live=1 to execute.
    MT4 balance op: AdmBalanceFix(login, cmd, value, comment). cmd 6=BALANCE, 7=CREDIT."""
    from flask import request
    live = request.args.get("live") == "1"
    try:
        u = _get_user_record(login)
        if not u:
            return jsonify({"login": login, "error": "user not found"}), 404
        bal, cred = u["balance"], u["credit"]
        if bal >= 0:
            return jsonify({"login": login, "status": "not_negative", "balance": bal})
        # Flat / PnL check (Model 4)
        try:
            all_trades = get_open_trades()
        except Exception:
            all_trades = []
        positions = [t for t in all_trades if t.get("login")==login and t.get("cmd") in (0,1)]
        floating = sum(float(t.get("profit",0)) for t in positions)
        if len(positions) > 0 and floating >= 10:
            return jsonify({"login": login, "status": "has_positions_positive_pnl", "floating_pnl": round(floating,2)})
        deficit = abs(bal)
        credit_to_take = min(cred, deficit) if cred > 0 else 0
        plan = {"login": login, "balance_before": bal, "credit_before": cred,
                "deficit": deficit, "credit_to_take": credit_to_take,
                "balance_after_planned": 0.0, "credit_after_planned": round(cred - credit_to_take, 2)}
        if not live:
            plan["status"] = "dry_run"
            plan["note"] = "No money moved. Add ?live=1 to execute."
            return jsonify(plan)
        # LIVE: balance first (+deficit), then credit out (-credit_to_take)
        man = get_manager()
        rc1 = vcall(man, V_ADM_BALANCE_FIX, c_int,
                    [c_int, c_int, c_double, c_char_p],
                    login, 6, float(deficit), b"Negative balance payoff")
        rc2 = None
        if credit_to_take > 0:
            rc2 = vcall(man, V_ADM_BALANCE_FIX, c_int,
                        [c_int, c_int, c_double, c_char_p],
                        login, 7, float(-credit_to_take), b"Credit Out")
        # Re-read
        u2 = _get_user_record(login)
        plan["status"] = "covered"
        plan["rc_balance"] = rc1
        plan["rc_credit"] = rc2
        plan["balance_after"] = u2["balance"] if u2 else None
        plan["credit_after"] = u2["credit"] if u2 else None
        return jsonify(plan)
    except Exception as e:
        return jsonify({"login": login, "status": "error", "error": str(e)}), 500

@app.route("/mt4/health", methods=["GET"])
def mt4_health():
    return jsonify({"status": "ok", "service": "mt4_bridge"})


if __name__ == "__main__":
    # Start sync in background so the web server is available immediately
    threading.Thread(target=sync_loop, daemon=True).start()
    log.info("MT4 bridge web server starting on http://0.0.0.0:5001")
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)











