# -*- coding: utf-8 -*-
"""离线逻辑自测：file_id 解码 / 创建时间估算 / ID 归一化"""
import base64
import os
import struct

os.environ.setdefault("BOT_TOKEN", "123456:TEST-TOKEN-FOR-OFFLINE-IMPORT")

import bot as B


def rle_encode(s: bytes) -> bytes:
    r = []
    n = 0
    for b in s:
        if not b:
            n += 1
        else:
            if n:
                r.extend((0, n))
                n = 0
            r.append(b)
    if n:
        r.extend((0, n))
    return bytes(r)


def make_file_id(dc_id, file_type=1, major=4, minor=30):
    payload = struct.pack("<ii", file_type, dc_id)
    payload += b"\x11" * 8          # media_id
    payload += b"\x22" * 4          # volume/access
    payload += struct.pack("<i", 3)  # thumbnail_source = CHAT_PHOTO_BIG
    payload += bytes([minor, major])
    return base64.urlsafe_b64encode(rle_encode(payload)).decode().strip("=")


ok = 0
fail = 0


def check(name, got, want):
    global ok, fail
    if got == want:
        ok += 1
        print(f"  PASS  {name}: {got}")
    else:
        fail += 1
        print(f"  FAIL  {name}: got={got!r} want={want!r}")


print("== file_id -> dc_id ==")
for dc in (1, 2, 3, 4, 5):
    check(f"v4 dc={dc}", B.decode_dc_id(make_file_id(dc)), dc)

# 带 flag 位的 file_type（WEB_LOCATION_FLAG / FILE_REFERENCE_FLAG）
for dc in (1, 5):
    check(f"flag-bits dc={dc}", B.decode_dc_id(make_file_id(dc, file_type=1 | (1 << 24) | (1 << 25))), dc)

# 旧版 major<4
check("v3 dc=2", B.decode_dc_id(make_file_id(2, major=3, minor=0)), 2)

print("== 异常输入 ==")
for bad in ["", "!!!!", "abc", "AAAA", None]:
    check(f"bad={bad!r}", B.decode_dc_id(bad), None)

print("== 创建时间估算 ==")
cases = [
    (1000, "2013年11月之前（≈2013年）"),
    (2768409, "2013年11月"),
    (100000000, "2015年03月"),
    (400169472, "2017年07月"),
    (805158066, "2019年07月"),
    (5170000000, "2022年02月"),
    (9000000000, "2025年11月之后"),
]
for uid, _ in cases:
    print(f"  id={uid:<12} -> {B.estimate_creation(uid)}")
check("anchor 2768409", B.estimate_creation(2768409), "2013年11月")
check("anchor 5170000000", B.estimate_creation(5170000000), "2022年02月")
check("too small", B.estimate_creation(1000), "2013年11月之前（≈2013年）")
check("too big", B.estimate_creation(9000000000), "2025年11月之后")
check("None", B.estimate_creation(None), None)
check("0", B.estimate_creation(0), None)

print("== 单调性检查（不能出现时间倒流）==")
prev = None
mono_ok = True
for i in range(0, 9000, 37):
    d = B.estimate_creation(i * 1000000 + 1)
    if prev is not None and d < prev:
        mono_ok = False
        print(f"  FAIL monotonic at {i * 1000000}: {prev} -> {d}")
    prev = d
check("单调递增", mono_ok, True)

print("== internal_id ==")
check("-1001234567890", B.internal_id(-1001234567890), 1234567890)
check("123456789", B.internal_id(123456789), 123456789)
check("-123456789 (普通群)", B.internal_id(-123456789), 123456789)

print("== 渲染 ==")
print(B.card_for_raw_id(123456789))
print("---")
print(B.card_for_raw_id(-1001234567890))

print(f"\n结果: {ok} passed, {fail} failed")
raise SystemExit(1 if fail else 0)
