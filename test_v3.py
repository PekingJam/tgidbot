# -*- coding: utf-8 -*-
"""验证 handler 过滤链：users_shared / chat_shared 必须真的被分发到"""
import os

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


def make(extra):
    d = {"message_id": 5, "date": 1700000000, "chat": {"id": 1, "type": "private"}, "from": {"id": 1, "is_bot": False, "first_name": "A"}}
    d.update(extra)
    return T.Message.de_json(d)


users_msg = make({"users_shared": {"request_id": 102, "users": [{"user_id": 777000, "first_name": "Telegram"}]}})
chat_msg = make({"chat_shared": {"request_id": 103, "chat_id": -1001234567890, "title": "T"}})
text_msg = make({"text": "hello"})


def matched(msg):
    return [h["function"].__name__ for h in B.bot.message_handlers
            if B.bot._test_message_handler(h, msg)]


print("== content_type ==")
check("users_shared", users_msg.content_type, "users_shared")
check("chat_shared", chat_msg.content_type, "chat_shared")

print("== 过滤链分发 ==")
mu = matched(users_msg)
print("  users_shared ->", mu)
check("命中 on_users_shared", "on_users_shared" in mu, True)
check("不误伤 on_text", "on_text" in mu, False)

mc = matched(chat_msg)
print("  chat_shared ->", mc)
check("命中 on_chat_shared", "on_chat_shared" in mc, True)

mt = matched(text_msg)
print("  text ->", mt)
check("文本命中 on_text", "on_text" in mt, True)
check("文本不命中 shared", ("on_users_shared" in mt) or ("on_chat_shared" in mt), False)

print("== handler 实跑（mock 掉出网）==")
sent = []
B.bot.send_message = lambda chat_id, text=None, **kw: sent.append((chat_id, text))
B.try_get_chat = lambda t: None
B.user_dc = lambda uid: None

B.on_users_shared(users_msg)
check("users_shared 发出 1 条", len(sent), 1)
check("内容含 ID", "777000" in (sent[0][1] or ""), True)
print(sent[0][1])

sent.clear()
B.on_chat_shared(chat_msg)
check("chat_shared 发出 1 条", len(sent), 1)
check("内容含 chat_id", "-1001234567890" in (sent[0][1] or ""), True)

print(f"\n结果: {ok} passed, {fail} failed")
raise SystemExit(1 if fail else 0)
