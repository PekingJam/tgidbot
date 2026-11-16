# -*- coding: utf-8 -*-
"""验证原生选择器键盘 + users_shared / chat_shared 渲染"""
import json
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


print("== 底部键盘结构 ==")
kb = B.main_keyboard()
payload = json.loads(kb.to_json())
rows = payload["keyboard"]
print(json.dumps(payload, ensure_ascii=False, indent=1))
check("行数", len(rows), 4)
check("第2行数", len(rows[1]), 2)
check("第3行数", len(rows[2]), 2)
check("群组用 request_chat", "request_chat" in rows[1][0], True)
check("群组 chat_is_channel", rows[1][0]["request_chat"]["chat_is_channel"], False)
check("频道 chat_is_channel", rows[1][1]["request_chat"]["chat_is_channel"], True)
check("用户用 request_users", "request_users" in rows[2][0], True)
check("用户 user_is_bot", rows[2][0]["request_users"]["user_is_bot"], False)
check("机器人 user_is_bot", rows[2][1]["request_users"]["user_is_bot"], True)
check("用户 max_quantity", rows[2][0]["request_users"]["max_quantity"], 1)
check("request_id 唯一",
      len({rows[1][0]["request_chat"]["request_id"],
           rows[1][1]["request_chat"]["request_id"],
           rows[2][0]["request_users"]["request_id"],
           rows[2][1]["request_users"]["request_id"]}), 4)
check("is_persistent", payload.get("is_persistent"), True)
check("resize_keyboard", payload.get("resize_keyboard"), True)

print("== main_menu 在群组返回 None ==")
check("group", B.main_menu("group"), None)
check("supergroup", B.main_menu("supergroup"), None)
check("private", isinstance(B.main_menu("private"), T.ReplyKeyboardMarkup), True)

print("== SharedUser 渲染（getChat 失败路径）==")
B.try_get_chat = lambda t: None
B.user_dc = lambda uid: None
u = T.SharedUser(user_id=777000, first_name="Telegram", username="telegram")
card = B.describe_shared_user(u, is_bot=True)
print(card)
check("含 ID", "777000" in card, True)
check("标为机器人", "机器人" in card, True)
check("含估算年份", "2013年" in card, True)

print("== ChatShared 渲染（getChat 失败路径）==")
cs = T.ChatShared(request_id=B.REQ_CHANNEL, chat_id=-1001006503122, title="Pavel Durov", username="durov")
card2 = B.describe_shared_chat(cs, is_channel=True)
print(card2)
check("含 chat_id", "-1001006503122" in card2, True)
check("标为频道", "频道" in card2, True)
check("含 username", "@durov" in card2, True)

cs_g = T.ChatShared(request_id=B.REQ_GROUP, chat_id=-1001234567890, title="某群")
card3 = B.describe_shared_chat(cs_g, is_channel=False)
check("群组标签", "类型</b>　群组" in card3, True)

print("== users_shared 反序列化 ==")
msg = T.Message.de_json({
    "message_id": 5, "date": 1700000000,
    "chat": {"id": 1, "type": "private"},
    "users_shared": {"request_id": 102, "users": [{"user_id": 777000, "first_name": "Telegram"}]},
})
check("users_shared 解析", msg.users_shared.users[0].user_id, 777000)
check("request_id 解析", msg.users_shared.request_id, B.REQ_BOT)

msg2 = T.Message.de_json({
    "message_id": 6, "date": 1700000000,
    "chat": {"id": 1, "type": "private"},
    "chat_shared": {"request_id": 103, "chat_id": -1001234567890, "title": "T"},
})
check("chat_shared 解析", msg2.chat_shared.chat_id, -1001234567890)

print(f"\n结果: {ok} passed, {fail} failed")
raise SystemExit(1 if fail else 0)
