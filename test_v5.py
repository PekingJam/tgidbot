# -*- coding: utf-8 -*-
"""验证使用统计：写入 / 计数 / /stats 权限"""
import os
import tempfile
import time

TMP = tempfile.mkdtemp()
os.environ["STATS_DB"] = os.path.join(TMP, "stats.db")
os.environ["ADMIN_IDS"] = "6999351766, 123456"
os.environ.setdefault("BOT_TOKEN", "123456:TEST-TOKEN-FOR-OFFLINE-IMPORT")

import telebot.types as T
import bot as B

ok = fail = 0


def check(name, got, want):
    global ok, fail
    if got == want:
        ok += 1
        print(f"  PASS  {name}")
    else:
        fail += 1
        print(f"  FAIL  {name}: got={got!r} want={want!r}")


def msg(uid, text=""):
    return T.Message.de_json({
        "message_id": 1, "date": int(time.time()),
        "chat": {"id": uid, "type": "private"},
        "from": {"id": uid, "is_bot": False, "first_name": "U"},
        "text": text,
    })


print("== 配置解析 ==")
check("ADMIN_IDS", sorted(B.ADMIN_IDS), [123456, 6999351766])
check("STATS_DB 生效", B.STATS_DB, os.environ["STATS_DB"])

print("== 写入与计数 ==")
B.record_use(msg(111), "user")
B.record_use(msg(111), "group")
B.record_use(msg(222), "channel")
check("今日次数", B._count(B._day_start(0), B._day_start(0) + 86400), (3, 2))

B.record_use(msg(333), "user")
check("再加一条", B._count(B._day_start(0), B._day_start(0) + 86400), (4, 3))

print("== 历史数据（伪造两天前）==")
import sqlite3
con = sqlite3.connect(B.STATS_DB)
old = B._day_start(2) + 3600
con.execute("INSERT INTO events(ts,kind,uid) VALUES(?,?,?)", (old, "user", 444))
con.commit(); con.close()
y_cnt, y_u = B._count(B._day_start(1), B._day_start(0))
check("昨日不计入两天前", (y_cnt, y_u), (0, 0))
w_cnt, w_u = B._count(B._day_start(6), B._day_start(0) + 86400)
check("近7天包含两天前", (w_cnt, w_u), (5, 4))

print("== stats_text ==")
t = B.stats_text()
print(t.replace("\n", "\n    "))
check("含今日", "今日" in t, True)
check("含累计", "累计" in t, True)
check("含首次记录", "首次记录" in t, True)

print("== 权限 ==")
sent = []
B.bot.send_message = lambda chat_id, text=None, **kw: sent.append(text)

B.cmd_stats(msg(999))          # 陌生人
check("陌生人静默", len(sent), 0)

B.cmd_stats(msg(6999351766))   # 管理员
check("管理员收到", len(sent), 1)
check("内容是统计", "📊" in (sent[0] or ""), True)

print("== record_use 容错 ==")
B.STATS_DB_OLD = B.STATS_DB
B.STATS_DB = "/proc/nonexistent/x.db"
B._db_inited = False
try:
    B.record_use(msg(1), "user")
    crashed = False
except Exception:
    crashed = True
check("库不可写时不抛异常", crashed, False)
B.STATS_DB = B.STATS_DB_OLD
B._db_inited = False

print(f"\n结果: {ok} passed, {fail} failed")
raise SystemExit(1 if fail else 0)
