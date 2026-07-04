import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from bridge_mt4 import load_dll, connect, get_manager, vcall, mem_free
from ctypes import c_int, c_void_p, c_char_p, POINTER, byref, string_at
import time

load_dll(); connect()
man = get_manager()
SERVERLOG_SIZE = 796
OFFSET_MSG = 284
from_time = int(time.time()) - 7 * 86400
to_time   = int(time.time())

# LOG_TYPE_FULL=4 to catch margin call / stop out messages
total = c_int(0)
ptr = vcall(man, 96, c_void_p,
            [c_int, c_int, c_int, c_char_p, POINTER(c_int)],
            2, from_time, to_time, b"", byref(total))

print(f"Trade journal records: {total.value}")
margin_msgs = []
stopout_msgs = []
for i in range(total.value):
    off = ptr + i * SERVERLOG_SIZE + OFFSET_MSG
    msg = string_at(off, 512).split(b"\x00")[0].decode("utf-8", errors="ignore")
    low = msg.lower()
    if "margin call" in low and len(margin_msgs) < 5:
        margin_msgs.append(msg)
    if "stop out" in low and len(stopout_msgs) < 5:
        stopout_msgs.append(msg)
mem_free(ptr)

print(f"\nMargin call samples:")
for m in margin_msgs: print(f"  {m[:130]}")
print(f"\nStop out samples:")
for m in stopout_msgs: print(f"  {m[:130]}")
