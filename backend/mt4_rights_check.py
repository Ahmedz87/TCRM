"""READ-ONLY: check MT4 provision login 3027's ManagerRights (can it modify users/groups?)."""
import os
os.environ["MT4_MGR_LOGIN"]="3027"
from ctypes import Structure, POINTER, byref, sizeof, c_int, c_uint, c_char
import bridge_mt4 as B
import mt_managers as _M
B.MT4_LOGIN, B.MT4_PASSWORD = _M.MT4["C"]
class ConManagerSec(Structure):
    _fields_=[("internal",c_int),("enable",c_int),("minimum_lots",c_int),("maximum_lots",c_int),("unused",c_int*16)]
class ConManager(Structure):
    _fields_=[("login",c_int),("manager",c_int),("money",c_int),("online",c_int),("riskman",c_int),
      ("broker",c_int),("admin",c_int),("logs",c_int),("reports",c_int),("trades",c_int),
      ("market_watch",c_int),("email",c_int),("user_details",c_int),("see_trades",c_int),("news",c_int),
      ("plugins",c_int),("server_reports",c_int),("techsupport",c_int),("market",c_int),("notifications",c_int),
      ("unused",c_int*9),("ipfilter",c_int),("ip_from",c_uint),("ip_to",c_uint),("mailbox",c_char*64),
      ("groups",c_char*1024),("secgroups",ConManagerSec*32),("exp_time",c_uint),("name",c_char*32),
      ("info_depth",c_int),("reserved",c_int*22)]
try:
    B.connect()
    man=B.get_manager()
    cm=ConManager()
    rc=B.vcall(man,14,c_int,[POINTER(ConManager)],byref(cm))
    print(f"rc={rc} login={cm.login} name={cm.name.decode('ascii','replace')}")
    for f in ["manager","admin","user_details","broker","trades","reports","money"]:
        print(f"   {f:14}= {getattr(cm,f)}")
    print("   managed groups:", cm.groups.decode('ascii','replace')[:60])
except Exception as e:
    print("ERROR:", e)
