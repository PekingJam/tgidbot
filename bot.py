#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram ID / DC 查询机器人
纯 Bot API 实现：ID、用户名、类型、估算创建时间、所在数据中心(DC)
"""
import base64
import html
import logging
import os
import re
import struct
import sys
from datetime import datetime, timedelta, timezone

import telebot
from telebot.apihelper import ApiTelegramException
from telebot.types import (
    KeyboardButton,
    KeyboardButtonRequestChat,
    KeyboardButtonRequestUsers,
    ReplyKeyboardMarkup,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
log = logging.getLogger("tgidbot")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    sys.exit("错误：未设置 BOT_TOKEN 环境变量")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# --------------------------------------------------------------------------
# 数据中心信息
# --------------------------------------------------------------------------
DC_INFO = {
    1: ("DC1", "美国 · 迈阿密", "🇺🇸"),
    2: ("DC2", "荷兰 · 阿姆斯特丹", "🇳🇱"),
    3: ("DC3", "美国 · 迈阿密", "🇺🇸"),
    4: ("DC4", "荷兰 · 阿姆斯特丹", "🇳🇱"),
    5: ("DC5", "新加坡", "🇸🇬"),
}


# --------------------------------------------------------------------------
# file_id -> dc_id 解码（Telegram 官方 file_id v4 格式）
# 结构: [file_type int32LE][dc_id int32LE]...+[minor u8][major u8]
# 整串做过 zero-RLE 压缩 + urlsafe base64(无 padding)
# --------------------------------------------------------------------------
def _b64_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _rle_decode(s: bytes) -> bytes:
    out = []
    zero = False
    for b in s:
        if not b:
            zero = True
            continue
        if zero:
            out.extend((0,) * b)
            zero = False
        else:
            out.append(b)
    return bytes(out)


def decode_dc_id(file_id: str):
    """从一个 file_id 里解出 dc_id，失败返回 None"""
    if not file_id:
        return None
    try:
        raw = _rle_decode(_b64_decode(file_id))
        if len(raw) < 10:
            return None
        _file_type, dc_id = struct.unpack("<ii", raw[:8])
        if 1 <= dc_id <= 5:
            return dc_id
        return None
    except Exception:
        return None


# --------------------------------------------------------------------------
# 用户 ID -> 注册时间估算（公开参考点 + 线性插值）
# --------------------------------------------------------------------------
_RAW_ANCHORS = [
    (2768409, "2013-11-01"), (7679610, "2013-12-31"), (11538514, "2014-01-31"),
    (15835244, "2014-02-20"), (23646077, "2014-02-26"), (38015510, "2014-03-01"),
    (44634663, "2014-05-05"), (46145305, "2014-05-15"), (54845238, "2014-09-20"),
    (63263518, "2014-10-27"), (101260938, "2015-03-06"), (101323197, "2015-03-12"),
    (103151531, "2015-06-04"), (103258382, "2015-05-27"), (109393468, "2015-08-08"),
    (111220210, "2015-04-20"), (112594714, "2015-08-15"), (116812045, "2015-07-24"),
    (122600695, "2015-07-24"), (124872445, "2015-08-18"), (125828524, "2015-10-04"),
    (130029930, "2015-09-03"), (133909606, "2015-10-07"), (143445125, "2015-12-01"),
    (148670295, "2016-01-07"), (152079341, "2016-01-21"), (157242073, "2015-11-06"),
    (171295414, "2016-03-08"), (181783990, "2016-04-09"), (222021233, "2016-06-08"),
    (225034354, "2016-06-18"), (278941742, "2016-09-09"), (285253072, "2016-10-18"),
    (294851037, "2016-11-20"), (297621225, "2016-12-15"), (328594461, "2016-12-28"),
    (337808429, "2017-02-21"), (341546272, "2017-02-22"), (352940995, "2017-02-23"),
    (369669043, "2017-03-30"), (400169472, "2017-07-30"), (805158066, "2019-07-15"),
    (1974255900, "2021-10-12"), (5027000000, "2021-12-15"), (5170000000, "2022-02-15"),
    (5351000000, "2022-05-15"), (5469000000, "2022-08-15"), (5720000000, "2022-11-15"),
    (5870000000, "2023-02-15"), (6001000000, "2023-05-15"), (6523000000, "2023-08-15"),
    (6647000000, "2023-11-15"), (6718000000, "2024-02-15"), (7095000000, "2024-05-15"),
    (7358000000, "2024-08-15"), (7665000000, "2024-11-15"), (7908000000, "2025-03-31"),
    (8190000000, "2025-08-15"), (8355000000, "2025-11-15"),
]


def _build_anchors():
    """整理成单调递增的 (id, datetime) 序列"""
    out = []
    last = None
    for uid, ds in _RAW_ANCHORS:
        dt = datetime.strptime(ds, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if last is not None and dt < last:
            dt = last
        out.append((uid, dt))
        last = dt
    return out


ANCHORS = _build_anchors()
ANCHOR_IDS = [a[0] for a in ANCHORS]
NOW = lambda: datetime.now(timezone.utc)


def estimate_creation(entity_id: int):
    """返回估算创建时间字符串，无法估算返回 None"""
    if entity_id is None or entity_id <= 0:
        return None
    if entity_id < ANCHOR_IDS[0]:
        return "2013年11月之前（≈2013年）"
    if entity_id > ANCHOR_IDS[-1]:
        return "2025年11月之后"

    lo = 0
    hi = len(ANCHOR_IDS) - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if ANCHOR_IDS[mid] <= entity_id:
            lo = mid
        else:
            hi = mid

    id_a, dt_a = ANCHORS[lo]
    id_b, dt_b = ANCHORS[hi]
    if id_b == id_a:
        est = dt_a
    else:
        ratio = (entity_id - id_a) / (id_b - id_a)
        est = dt_a + timedelta(seconds=(dt_b - dt_a).total_seconds() * ratio)
    return f"{est.year}年{est.month:02d}月"


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------
def esc(s) -> str:
    return html.escape(str(s)) if s is not None else ""


def fmt_dc(dc_id):
    if not dc_id:
        return "未知 <i>（该对象无头像，无法定位 DC）</i>"
    info = DC_INFO.get(dc_id)
    if not info:
        return f"DC{dc_id}"
    return f"{info[2]} {info[0]} · {info[1]}"


TYPE_CN = {
    "private": "用户 / 机器人（私聊）",
    "group": "普通群组",
    "supergroup": "超级群组",
    "channel": "频道",
}


def internal_id(chat_id: int) -> int:
    """把 -100xxxxxxxxxx 的超级群/频道 ID 还原成内部递增序号"""
    if chat_id is None:
        return 0
    if chat_id < 0:
        s = str(-chat_id)
        if s.startswith("100") and len(s) > 10:
            return int(s[3:])
        return -chat_id if chat_id > -1000000000000 else 0
    return chat_id


def user_dc(user_id: int):
    """通过用户头像的 file_id 解码 DC"""
    try:
        photos = bot.get_user_profile_photos(user_id, offset=0, limit=1)
    except ApiTelegramException as e:
        log.warning("getUserProfilePhotos(%s) 失败: %s", user_id, e)
        return None
    if not photos or not photos.photos:
        return None
    sizes = photos.photos[0]
    for ps in reversed(sizes):
        dc = decode_dc_id(ps.file_id)
        if dc:
            return dc
    return None


def chat_dc(chat):
    try:
        photo = getattr(chat, "photo", None)
        if photo and getattr(photo, "big_file_id", None):
            return decode_dc_id(photo.big_file_id)
    except Exception:
        pass
    return None


# --------------------------------------------------------------------------
# 卡片渲染
# --------------------------------------------------------------------------
HEADER = "<b>{icon} {title}</b>\n\n"


def card_for_chat(chat, is_bot=None) -> str:
    ctype = getattr(chat, "type", "private")
    cid = getattr(chat, "id", 0)

    if ctype == "private":
        dc = user_dc(cid)
    else:
        dc = chat_dc(chat) or None

    if is_bot is True:
        subj = "机器人"
    elif is_bot is False:
        subj = "用户"
    else:
        subj = "用户 / 机器人（私聊）"

    lines = []
    if ctype == "private":
        name = " ".join(
            x for x in [getattr(chat, "first_name", None), getattr(chat, "last_name", None)] if x
        ) or "（无名字）"
        lines.append(f"<b>名称</b>　{esc(name)}")
        lines.append(f"<b>类型</b>　{subj}")
        lines.append(f"<b>用户名</b>　{('@' + esc(chat.username)) if getattr(chat, 'username', None) else '无'}")
        lines.append(f"<b>数字 ID</b>　<code>{cid}</code>")
        est = estimate_creation(cid)
        lines.append(f"<b>创建时间</b>　{est or '未知'} <i>(按 ID 估算，仅供参考)</i>")
        lines.append(f"<b>所在地区</b>　{fmt_dc(dc)}")
        head = HEADER.format(icon="👤", title="账号信息")
    else:
        title = getattr(chat, "title", None) or "（无标题）"
        lines.append(f"<b>标题</b>　{esc(title)}")
        lines.append(f"<b>类型</b>　{TYPE_CN.get(ctype, ctype)}")
        lines.append(f"<b>用户名</b>　{('@' + esc(chat.username)) if getattr(chat, 'username', None) else '无'}")
        lines.append(f"<b>数字 ID</b>　<code>{cid}</code>")
        if ctype == "group":
            lines.append("<b>创建时间</b>　未知 <i>(普通群组无法估算)</i>")
        else:
            est = estimate_creation(internal_id(cid))
            lines.append(f"<b>创建时间</b>　{est or '未知'} <i>(按 ID 估算，仅供参考)</i>")
        lines.append(f"<b>所在地区</b>　{fmt_dc(dc)}")
        head = HEADER.format(icon="📣", title="频道信息" if ctype == "channel" else "群组信息")

    if getattr(chat, "description", None):
        desc = chat.description.replace("\n", " ")
        if len(desc) > 120:
            desc = desc[:120] + "…"
        lines.append(f"<b>简介</b>　{esc(desc)}")

    return head + "\n".join(lines)


def card_for_raw_id(raw_id: int) -> str:
    """拿不到 Chat 对象时，只按 ID 出卡片"""
    is_chat = raw_id < 0
    if is_chat:
        s = str(-raw_id)
        is_super = s.startswith("100") and len(s) > 10
        est = estimate_creation(internal_id(raw_id)) if is_super else None
        est_line = (
            f"<b>创建时间</b>　{est} <i>(按 ID 估算，仅供参考)</i>\n"
            if est
            else "<b>创建时间</b>　未知 <i>(普通群组无法估算)</i>\n"
        )
        return (
            HEADER.format(icon="📣", title="ID 信息")
            + f"<b>数字 ID</b>　<code>{raw_id}</code>\n"
            + est_line
            + "<b>所在地区</b>　未知\n\n"
            + "<i>机器人无权读取该聊天详情，请把它的消息转发给我以获得完整信息。</i>"
        )
    est = estimate_creation(raw_id)
    return (
        HEADER.format(icon="👤", title="ID 信息")
        + f"<b>数字 ID</b>　<code>{raw_id}</code>\n"
        + f"<b>创建时间</b>　{est or '未知'} <i>(按 ID 估算，仅供参考)</i>\n"
        + "<b>所在地区</b>　未知\n\n"
        + "<i>机器人无法读取该用户资料（对方从未与本机器人交互）。请把对方的一条消息<b>转发</b>给我。</i>"
    )


# --------------------------------------------------------------------------
# 目标解析
# --------------------------------------------------------------------------
def try_get_chat(target):
    try:
        return bot.get_chat(target)
    except ApiTelegramException as e:
        log.info("getChat(%s) 失败: %s", target, e)
        return None
    except Exception as e:
        log.warning("getChat(%s) 异常: %s", target, e)
        return None


def resolve_and_reply(m: telebot.types.Message, target, note: str = "", is_bot=None):
    chat = try_get_chat(target)
    if chat is not None:
        text = card_for_chat(chat, is_bot=is_bot)
    else:
        raw = target if isinstance(target, int) else None
        if raw is None:
            bot.send_message(
                m.chat.id,
                f"❌ 查不到 <code>{esc(target)}</code>。\n"
                "可能原因：用户名不存在、对方是私有对象，或机器人从未见过它。\n"
                "试试把对方的消息<b>转发</b>给我。",
                reply_markup=main_menu(m.chat.type),
            )
            return
        text = card_for_raw_id(raw)
    if note:
        text += f"\n\n<i>{esc(note)}</i>"
    bot.send_message(m.chat.id, text, reply_markup=main_menu(m.chat.type), disable_web_page_preview=True)


# --------------------------------------------------------------------------
# 菜单
# --------------------------------------------------------------------------
REQ_USER = 101
REQ_BOT = 102
REQ_GROUP = 103
REQ_CHANNEL = 104


def main_keyboard() -> ReplyKeyboardMarkup:
    """底部常驻键盘：四个按钮直接调起 Telegram 原生选择器"""
    kb = ReplyKeyboardMarkup(resize_keyboard=True, is_persistent=True)
    kb.row(KeyboardButton("👤 我的 ID"))
    kb.row(
        KeyboardButton(
            "👥 群组",
            request_chat=KeyboardButtonRequestChat(
                REQ_GROUP, chat_is_channel=False,
                request_title=True, request_username=True,
            ),
        ),
        KeyboardButton(
            "📣 频道",
            request_chat=KeyboardButtonRequestChat(
                REQ_CHANNEL, chat_is_channel=True,
                request_title=True, request_username=True,
            ),
        ),
    )
    kb.row(
        KeyboardButton(
            "👤 用户",
            request_users=KeyboardButtonRequestUsers(
                REQ_USER, user_is_bot=False, max_quantity=1,
                request_name=True, request_username=True, request_photo=True,
            ),
        ),
        KeyboardButton(
            "🤖 机器人",
            request_users=KeyboardButtonRequestUsers(
                REQ_BOT, user_is_bot=True, max_quantity=1,
                request_name=True, request_username=True, request_photo=True,
            ),
        ),
    )
    kb.row(KeyboardButton("📖 使用说明"))
    return kb


def main_menu(chat_type: str = None):
    """私聊才挂底部键盘；群组里返回 None 避免污染群聊"""
    if chat_type and chat_type != "private":
        return None
    return main_keyboard()


HOW_TEXT = {
    "user": (
        "👤 <b>查询用户</b>\n\n"
        "任选一种方式发给我：\n"
        "1️⃣ 把该用户的一条消息 <b>转发</b> 给我（最准）\n"
        "2️⃣ 发送 <code>@用户名</code>\n"
        "3️⃣ 发送数字 ID，例如 <code>123456789</code>"
    ),
    "bot": (
        "🤖 <b>查询机器人</b>\n\n"
        "任选一种方式发给我：\n"
        "1️⃣ 发送 <code>@xxx_bot</code>\n"
        "2️⃣ 把该机器人的一条消息 <b>转发</b> 给我\n"
        "3️⃣ 发送数字 ID"
    ),
    "channel": (
        "📣 <b>查询频道</b>\n\n"
        "任选一种方式发给我：\n"
        "1️⃣ 把频道里的一条消息 <b>转发</b> 给我（最准）\n"
        "2️⃣ 发送 <code>@频道用户名</code> 或 <code>t.me/xxx</code> 链接\n"
        "3️⃣ 发送数字 ID，例如 <code>-1001234567890</code>"
    ),
    "group": (
        "👥 <b>查询群组</b>\n\n"
        "任选一种方式发给我：\n"
        "1️⃣ 把群里的一条消息 <b>转发</b> 给我（最准）\n"
        "2️⃣ 发送 <code>@群用户名</code> 或 <code>t.me/xxx</code> 链接\n"
        "3️⃣ 发送数字 ID，例如 <code>-1001234567890</code>"
    ),
}


def help_text() -> str:
    return (
        "<b>📖 使用说明</b>\n\n"
        "<b>底部按钮（推荐）</b>\n"
        "👥 群组 · 📣 频道 · 👤 用户 · 🤖 机器人\n"
        "点一下就弹出 Telegram 原生列表，搜名字或用户名，选中即可\n\n"
        "<b>快捷指令</b>\n"
        "/id — 获取你自己的 ID（在群里用会同时给出群 ID）\n"
        "/dc — 发送一张图片/文件，反查它所在的 DC\n"
        "/start — 打开主菜单\n"
        "/help — 本说明\n\n"
        "<b>也支持直接发</b>\n"
        "• 转发一条消息 → 解析发送者 / 来源频道\n"
        "• 分享联系人 → 解析该用户（需先把他存进通讯录，否则 Telegram 不给 ID）\n"
        "• 发 <code>@用户名</code>\n"
        "• 发数字 ID\n\n"
        "<b>字段说明</b>\n"
        "• <b>数字 ID</b>：Telegram 唯一标识，永久不变\n"
        "• <b>创建时间</b>：Telegram 不公开真实注册时间，这里按 ID 递增规律估算，误差可达数月\n"
        "• <b>所在地区</b>：从对象头像的 file_id 解出数据中心（DC）编号后映射机房位置。没有头像就查不到"
    )


# --------------------------------------------------------------------------
# 指令
# --------------------------------------------------------------------------
@bot.message_handler(commands=["start"])
def cmd_start(m: telebot.types.Message):
    name = esc(m.from_user.first_name or "朋友")
    bot.send_message(
        m.chat.id,
        f"嗨 {name}，我是 ID 查询鲸鱼 🐳\n\n"
        "点底部的 <b>群组 / 频道 / 用户 / 机器人</b>，会弹出 Telegram 原生列表，"
        "选中目标我就返回它的 ID、创建时间和所在地区。\n\n"
        "也可以直接<b>转发</b>一条消息，或者发 <code>@用户名</code> / 数字 ID。",
        reply_markup=main_menu(m.chat.type),
    )


@bot.message_handler(commands=["help"])
def cmd_help(m: telebot.types.Message):
    bot.send_message(m.chat.id, help_text(), reply_markup=main_menu(m.chat.type))


@bot.message_handler(commands=["id", "me", "myid"])
def cmd_id(m: telebot.types.Message):
    # 先回自己的信息
    chat = try_get_chat(m.from_user.id)
    if chat is not None:
        text = card_for_chat(chat)
    else:
        text = card_for_raw_id(m.from_user.id)
    # 群组里额外给出当前群信息
    if m.chat.type in ("group", "supergroup", "channel"):
        gchat = try_get_chat(m.chat.id)
        text += "\n\n" + ("─" * 14) + "\n\n"
        text += card_for_chat(gchat) if gchat is not None else card_for_raw_id(m.chat.id)
    bot.send_message(m.chat.id, text, reply_markup=main_menu(m.chat.type), disable_web_page_preview=True)


@bot.message_handler(commands=["dc"])
def cmd_dc(m: telebot.types.Message):
    bot.send_message(
        m.chat.id,
        "发一张图片（或任意文件）给我，我从它的 file_id 里解出所在数据中心。\n"
        "<i>提示：你自己上传的文件通常落在你所属的 DC 上。</i>",
    )


# --------------------------------------------------------------------------
# 回调
# --------------------------------------------------------------------------
@bot.callback_query_handler(func=lambda c: True)
def on_callback(c: telebot.types.CallbackQuery):
    data = c.data or ""
    try:
        bot.answer_callback_query(c.id)
    except Exception:
        pass

    if data == "me":
        chat = try_get_chat(c.from_user.id)
        text = card_for_chat(chat) if chat is not None else card_for_raw_id(c.from_user.id)
        bot.send_message(c.message.chat.id, text, reply_markup=main_menu(c.message.chat.type),
                         disable_web_page_preview=True)
    elif data.startswith("how:"):
        kind = data.split(":", 1)[1]
        bot.send_message(c.message.chat.id, HOW_TEXT.get(kind, "未知选项"),
                         reply_markup=main_menu(c.message.chat.type))
    elif data in ("help", "back"):
        bot.send_message(c.message.chat.id, help_text(), reply_markup=main_menu(c.message.chat.type))


# --------------------------------------------------------------------------
# 媒体 -> DC
# --------------------------------------------------------------------------
@bot.message_handler(
    content_types=["photo", "document", "video", "audio", "voice", "animation", "video_note", "sticker"]
)
def on_media(m: telebot.types.Message):
    fid = None
    if m.photo:
        fid = m.photo[-1].file_id
    elif m.document:
        fid = m.document.file_id
    elif m.video:
        fid = m.video.file_id
    elif m.audio:
        fid = m.audio.file_id
    elif m.voice:
        fid = m.voice.file_id
    elif m.animation:
        fid = m.animation.file_id
    elif m.video_note:
        fid = m.video_note.file_id
    elif m.sticker:
        fid = m.sticker.file_id

    dc = decode_dc_id(fid)
    if dc:
        bot.send_message(
            m.chat.id,
            f"🗄 <b>文件所在数据中心</b>　{fmt_dc(dc)}\n\n"
            "<i>由 file_id 直接解码得出，无需下载文件。</i>",
            reply_markup=main_menu(m.chat.type),
        )
    else:
        bot.send_message(
            m.chat.id,
            "❌ 从该文件的 file_id 里没能解出 DC 编号。\n"
            "换个文件试试，或者它可能是特殊类型的外链文件。",
            reply_markup=main_menu(m.chat.type),
        )


# --------------------------------------------------------------------------
# 分享联系人（用户主页 → 右上角三点 → 分享联系人）
# --------------------------------------------------------------------------
@bot.message_handler(content_types=["contact"])
def on_contact(m: telebot.types.Message):
    c = m.contact
    uid = getattr(c, "user_id", None)
    log.info("收到 contact: user_id=%s has_phone=%s", uid, bool(c.phone_number))

    if not uid:
        bot.send_message(
            m.chat.id,
            "🙈 这个联系人没带 Telegram 用户 ID，查不了。\n\n"
            "原因：<b>对方不在你的通讯录里</b>，Telegram 只分享了名字和号码，"
            "而号码不能反查 ID。\n\n"
            "换成底部「👤 用户」按钮选一次，或者把对方的消息<b>转发</b>给我。",
            reply_markup=main_menu(m.chat.type),
        )
        return

    try:
        text = describe_contact_user(c)
    except Exception as e:
        log.exception("渲染联系人失败")
        text = f"❌ 解析失败：{esc(e)}"
    bot.send_message(
        m.chat.id, text,
        reply_markup=main_menu(m.chat.type),
        disable_web_page_preview=True,
    )


def describe_contact_user(c) -> str:
    uid = c.user_id
    chat = try_get_chat(uid)
    if chat is not None:
        return card_for_chat(chat)

    dc = user_dc(uid)
    name = " ".join(x for x in [c.first_name, c.last_name] if x) or "（无名字）"
    lines = [
        f"<b>名称</b>　{esc(name)}",
        "<b>类型</b>　用户 / 机器人（私聊）",
        "<b>用户名</b>　无 <i>(分享联系人里不含用户名)</i>",
        f"<b>数字 ID</b>　<code>{uid}</code>",
        f"<b>创建时间</b>　{estimate_creation(uid) or '未知'} <i>(按 ID 估算，仅供参考)</i>",
        f"<b>所在地区</b>　{fmt_dc(dc)}",
    ]
    return HEADER.format(icon="👤", title="账号信息") + "\n".join(lines)


# --------------------------------------------------------------------------
# 原生选择器回传（users_shared / chat_shared）
# --------------------------------------------------------------------------
def _dc_from_photo_list(photos):
    for ps in reversed(photos or []):
        dc = decode_dc_id(getattr(ps, "file_id", None))
        if dc:
            return dc
    return None


def describe_shared_user(u, is_bot=None) -> str:
    chat = try_get_chat(u.user_id)
    if chat is not None:
        return card_for_chat(chat, is_bot=is_bot)

    dc = _dc_from_photo_list(getattr(u, "photo", None))
    if not dc:
        dc = user_dc(u.user_id)

    name = " ".join(x for x in [u.first_name, u.last_name] if x) or "（无名字）"
    subj = "机器人" if is_bot else ("用户" if is_bot is False else "用户 / 机器人（私聊）")
    lines = [
        f"<b>名称</b>　{esc(name)}",
        f"<b>类型</b>　{subj}",
        f"<b>用户名</b>　{('@' + esc(u.username)) if getattr(u, 'username', None) else '无'}",
        f"<b>数字 ID</b>　<code>{u.user_id}</code>",
        f"<b>创建时间</b>　{estimate_creation(u.user_id) or '未知'} <i>(按 ID 估算，仅供参考)</i>",
        f"<b>所在地区</b>　{fmt_dc(dc)}",
    ]
    return HEADER.format(icon="🤖" if is_bot else "👤", title="机器人信息" if is_bot else "账号信息") + "\n".join(lines)


def describe_shared_chat(cs, is_channel: bool) -> str:
    chat = try_get_chat(cs.chat_id)
    if chat is not None:
        return card_for_chat(chat)

    dc = _dc_from_photo_list(getattr(cs, "photo", None))
    est = estimate_creation(internal_id(cs.chat_id))
    lines = [
        f"<b>标题</b>　{esc(cs.title or '（无标题）')}",
        f"<b>类型</b>　{'频道' if is_channel else '群组'}",
        f"<b>用户名</b>　{('@' + esc(cs.username)) if getattr(cs, 'username', None) else '无'}",
        f"<b>数字 ID</b>　<code>{cs.chat_id}</code>",
        f"<b>创建时间</b>　{est or '未知'} <i>(按 ID 估算，仅供参考)</i>",
        f"<b>所在地区</b>　{fmt_dc(dc)}",
    ]
    icon = "📣" if is_channel else "👥"
    title = "频道信息" if is_channel else "群组信息"
    return HEADER.format(icon=icon, title=title) + "\n".join(lines)


@bot.message_handler(
    func=lambda m: getattr(m, "users_shared", None) is not None,
    content_types=["users_shared"],
)
def on_users_shared(m: telebot.types.Message):
    log.info("收到 users_shared: request_id=%s users=%s",
             m.users_shared.request_id, len(getattr(m.users_shared, "users", None) or []))
    shared = m.users_shared
    is_bot = {REQ_BOT: True, REQ_USER: False}.get(shared.request_id)
    users = getattr(shared, "users", None) or []
    if not users:
        bot.send_message(m.chat.id, "没有选到用户，再试一次吧。", reply_markup=main_menu(m.chat.type))
        return
    for u in users[:10]:
        try:
            text = describe_shared_user(u, is_bot)
        except Exception as e:
            log.exception("渲染共享用户失败")
            text = f"❌ 解析失败：{esc(e)}"
        bot.send_message(
            m.chat.id, text,
            reply_markup=main_menu(m.chat.type),
            disable_web_page_preview=True,
        )


@bot.message_handler(
    func=lambda m: getattr(m, "chat_shared", None) is not None,
    content_types=["chat_shared"],
)
def on_chat_shared(m: telebot.types.Message):
    cs = m.chat_shared
    log.info("收到 chat_shared: request_id=%s chat_id=%s", cs.request_id, cs.chat_id)
    is_channel = cs.request_id == REQ_CHANNEL
    try:
        text = describe_shared_chat(cs, is_channel)
    except Exception as e:
        log.exception("渲染共享聊天失败")
        text = f"❌ 解析失败：{esc(e)}"
    bot.send_message(
        m.chat.id, text,
        reply_markup=main_menu(m.chat.type),
        disable_web_page_preview=True,
    )


# --------------------------------------------------------------------------
# 转发消息 / 文本解析
# --------------------------------------------------------------------------
def entity_from_forward(m: telebot.types.Message):
    """从转发消息里取出 (目标, 备注, is_bot)"""
    fo = getattr(m, "forward_origin", None)
    if fo is not None:
        otype = getattr(fo, "type", "")
        if otype == "user":
            u = fo.sender_user
            return u.id, f"来源：{u.first_name or ''} 转发的消息", getattr(u, "is_bot", None)
        if otype == "hidden_user":
            return None, f"该用户开启了隐私保护，仅显示昵称：{fo.sender_user_name}", None
        if otype == "chat":
            return fo.sender_chat.id, "来源：用户转发", None
        if otype == "channel":
            return fo.chat.id, "来源：频道转发", None
    # 旧版字段兼容
    if getattr(m, "forward_from", None):
        return m.forward_from.id, "来源：转发的用户消息", getattr(m.forward_from, "is_bot", None)
    if getattr(m, "forward_from_chat", None):
        return m.forward_from_chat.id, "来源：转发的聊天消息", None
    if getattr(m, "forward_sender_name", None):
        return None, f"该用户开启了隐私保护，仅显示昵称：{m.forward_sender_name}", None
    return None, None, None


@bot.message_handler(func=lambda m: True, content_types=["text"])
def on_text(m: telebot.types.Message):
    text = (m.text or "").strip()

    # 0) 底部键盘里的纯文本按钮
    norm = text.lstrip("👤🤖👥📣📖🔍 ").strip()
    if norm in ("我的 ID", "我的ID"):
        return cmd_id(m)
    if norm == "使用说明":
        return cmd_help(m)
    if norm in ("用户", "群组", "频道", "机器人"):
        bot.send_message(
            m.chat.id,
            "这个按钮靠 Telegram 客户端弹出原生列表，需要较新的版本才能用。\n\n"
            "如果没弹出来，可以把目标的消息<b>转发</b>给我，效果一样。",
            reply_markup=main_menu(m.chat.type),
        )
        return

    # 1) 转发消息优先
    target, note, is_bot = entity_from_forward(m)
    if target is not None:
        resolve_and_reply(m, target, note or "", is_bot=is_bot)
        return
    if target is None and note:
        bot.send_message(m.chat.id, f"🙈 {note}\n\n这种情况拿不到数字 ID，只能拿到昵称。", reply_markup=main_menu(m.chat.type))
        return

    # 2) t.me 链接
    tl = re.search(r"(?:https?://)?t(?:elegram)?\.(?:me|dog)/(?:joinchat/)?([A-Za-z0-9_+\-]+)", text)
    if tl:
        slug = tl.group(1)
        resolve_and_reply(m, slug if slug.startswith("+") else "@" + slug)
        return

    # 3) @username
    um = re.fullmatch(r"@([A-Za-z0-9_]{4,64})", text)
    if um:
        resolve_and_reply(m, "@" + um.group(1))
        return

    # 4) 纯数字 ID
    idm = re.fullmatch(r"-?\d{4,20}", text)
    if idm:
        resolve_and_reply(m, int(idm.group(0)))
        return

    bot.send_message(
        m.chat.id,
        "没看懂这条输入 🤔\n\n可以：\n"
        "• 转发一条消息给我\n"
        "• 发 <code>@用户名</code>\n"
        "• 发数字 ID\n"
        "• 发一张图片查 DC\n\n"
        "点下方按钮看教程。",
        reply_markup=main_menu(m.chat.type),
    )


# --------------------------------------------------------------------------
if __name__ == "__main__":
    me = bot.get_me()
    log.info("启动成功：@%s (id=%s)", me.username, me.id)
    try:
        bot.set_my_commands([
            telebot.types.BotCommand("id", "获取当前用户 ID"),
            telebot.types.BotCommand("dc", "反查文件所在数据中心"),
            telebot.types.BotCommand("start", "打开主菜单"),
            telebot.types.BotCommand("help", "使用说明"),
        ])
        log.info("命令菜单已更新")
    except Exception as e:
        log.warning("设置命令菜单失败: %s", e)
    bot.infinity_polling(skip_pending=True, timeout=30)
