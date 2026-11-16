# -*- coding: utf-8 -*-
"""验证 contact（分享联系人）消息能被分发并回复"""
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
    d = {"message_id": 7, "date": 1700000000, "chat": {"id": 1, "type": "private"},
         "from": {"id": 1, "is_bot": False, "first_name": "A"}}
    d.update(extra)
    return T.Message.de_json(d)


with_id = make({"contact": {"phone_number": "+8613800000000", "first_name": "张三",
                            "last_name": "李", "user_id": 777000}})
no_id = make({"contact": {"phone_number": "+8613900000000", "first_name": "王五"}})

print("== 解析 ==")
check("content_type", with_id.content_type, "contact")
check("user_id", with_id.contact.user_id, 777000)
check("无 user_id 时为 None", no_id.contact.user_id, None)
check("first_name", with_id.contact.first_name, "张三")

print("== 分发链 ==")


def matched(msg):
    return [h["function"].__name__ for h in B.bot.message_handlers
            if B.bot._test_message_handler(h, msg)]


m = matched(with_id)
print("  contact ->", m)
check("命中 on_contact", "on_contact" in m, True)
check("不误伤 on_text", "on_text" in m, False)
check("不误伤 on_media", "on_media" in m, False)

print("== handler 实跑 ==")
sent = []
B.bot.send_message = lambda chat_id, text=None, **kw: sent.append(text)
B.try_get_chat = lambda t: None
B.user_dc = lambda uid: None

B.on_contact(with_id)
check("有 ID 时回复 1 条", len(sent), 1)
check("含数字 ID", "777000" in sent[0], True)
check("含姓名", "张三" in sent[0], True)
print(sent[0])

sent.clear()
B.on_contact(no_id)
check("无 ID 时也给回复", len(sent), 1)
check("提示拿不到 ID", "查不了" in sent[0], True)
print(sent[0])

print(f"\n结果: {ok} passed, {fail} failed")
raise SystemExit(1 if fail else 0)
