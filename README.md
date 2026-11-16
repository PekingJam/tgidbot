# tgidbot — Telegram ID / DC 查询机器人

纯 Bot API 实现，不需要用户账号、不需要 MTProto。查用户 / 机器人 / 频道 / 群组的：

- 数字 ID
- 用户名
- 类型
- 创建时间（按 ID 估算）
- 所在地区（解 file_id 得到 DC，映射机房位置）

## 部署

```bash
cd /home/orange/tgidbot
cp .env.example .env
# 把 BOT_TOKEN 填进去
docker compose up -d --build
docker compose logs -f
```

## 用法

| 操作 | 说明 |
|---|---|
| `/start` | 弹出底部常驻键盘 |
| 底部 **👥 群组 / 📣 频道 / 👤 用户 / 🤖 机器人** | 调起 Telegram 原生选择器，直接点选目标 |
| `/id` | 获取自己的 ID（群里用会同时给出群 ID） |
| `/dc` | 发一张图片/文件，反查它所在 DC |
| `/stats` | 使用统计（**仅管理员**，见下） |
| `/help` | 使用说明 |
| 转发任意消息 | 自动解析发送者 / 来源频道 |
| 发 `@username` | 解析该账号 |
| 发数字 ID | 解析该对象 |
| 发 `t.me/xxx` | 解析该链接 |

### 底部按钮的原理

用的是 `ReplyKeyboardMarkup` + `KeyboardButton` 的 **`request_users` / `request_chat`**
（Bot API 7.0+）：

- `request_chat(chat_is_channel=False)` → 弹出「选择群组」，回传 `chat_shared`
- `request_chat(chat_is_channel=True)` → 弹出「选择频道」，回传 `chat_shared`
- `request_users(user_is_bot=False)` → 弹出「选择用户」，回传 `users_shared`
- `request_users(user_is_bot=True)` → 只列机器人

回传的 `SharedUser` / `ChatShared` 里**已经带 first_name / username / title /
photo**，所以即使 `getChat` 失败也能直接出卡片 —— 比转发消息更省事，也不用装
`InlineKeyboard`。选择器本身由客户端渲染，可以搜名字或用户名。

注意：`request_*` 按钮**只能在和 bot 的私聊里用**，所以群组里不发这套键盘。

## 使用统计（`/stats`）

Bot API 不提供任何 bot 使用数据接口，所以自带一个极简埋点：

- 每次成功返回结果记一条 `(时间戳, 查询类型, 发起者 user_id)`
- **不记录被查询对象** —— 公开 bot 记下「谁查过谁」就成了隐私问题
- 数据存 SQLite：宿主机 `./data/stats.db`，容器内 `/data/stats.db`

`/stats` 只对 `.env` 里 `ADMIN_IDS` 白名单中的人生效，其他人发这个命令**完全静默**，连这个命令存在都看不出来。

```bash
ADMIN_IDS=你的TG_ID,另一个ID
```

输出今日 / 昨日 / 近 7 天 / 累计的查询次数与去重人数。

## 关于「所在地区」的原理

Bot API 没有 `dc_id` 字段。本机器人用 `getUserProfilePhotos` / `getChat` 拿到头像的
`file_id`，按 Telegram 官方 file_id v4 布局解码：

```
[file_type int32 LE][dc_id int32 LE] ...... [minor u8][major u8]
整串经过 zero-RLE 压缩 + urlsafe base64(无 padding)
```

DC 与机房对应关系：

- DC1 / DC3 → 美国 迈阿密
- DC2 / DC4 → 荷兰 阿姆斯特丹
- DC5 → 新加坡

**前提是该对象有头像。** 没有头像就解不出 DC，卡片会显示「未知」。

## 关于「创建时间」

Telegram 不公开任何账号的真实注册时间。本机器人用公开的 ID→时间参考点（2013-11 至
2025-11，59 个点）做线性插值，结果是**估算**，稀疏年份误差可达数月甚至两年。

频道/超级群组用 `-100xxxxxxxxxx` 还原出的内部序号估算，误差更大，仅供参考。

## 限制（如实说明）

1. **用户没有头像 → 查不到 DC**，这是 Bot API 的硬限制，只能上 Telethon/TDLib 用户账号才准。
2. **bot 没见过的用户**（从未与 bot 交互、也没被转发过）无法 `getChat`，只能显示 ID + 估算时间。
3. 用户在隐私设置里开了「转发消息时隐藏发件人」时，只能拿到昵称，拿不到 ID。
4. 想在群组里直接 `/id` 生效，需要去 @BotFather 用 `/setprivacy` 关闭 Group Privacy；
   不关也能用 —— 转发消息始终可用。
