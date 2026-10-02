# astrbot_plugin_daily_ai_news

每日 AI 资讯自动推送插件 - 为 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 开发

通过 RSS 订阅 [橘鸦 AI 日报](https://daily.juya.uk/rss.xml) 获取最新 AI 早报，经 **AI 总结** 后自动推送到 QQ 群 / 私聊。

本仓库 fork 自 [xxofficial/astrbot_plugin_daily_ai_news](https://github.com/xxofficial/astrbot_plugin_daily_ai_news)，修正了 `metadata.yaml` 中版本号的类型，使其满足 AstrBot 4.28.0 的安装元数据校验。

## ✨ 功能

- 📰 **每日自动推送**：每天定时（默认早 8:00）自动推送最新 AI 资讯
- 🤖 **AI 智能总结**：调用 AstrBot 内置 LLM，将长篇早报精炼为 5-8 条关键要点
- 🔄 **手动获取**：发送 `/ainews` 随时获取最新 AI 资讯
- 📋 **灵活订阅**：支持配置文件填写群号/QQ号 + 群内指令订阅两种方式
- ⏳ **智能轮询**：若 RSS 尚未更新当日内容，插件会自动间隔轮询直到获取到当日文章
- 💾 **缓存去重**：AI 总结结果会缓存到本地，避免重复调用 LLM；已推送文章自动去重

## 📝 指令列表

| 指令             | 说明                              |
| ---------------- | --------------------------------- |
| `/ainews`        | 立即获取最新 AI 资讯（AI 总结版） |
| `/ainews_sub`    | 订阅每日推送（群聊/私聊均可使用） |
| `/ainews_unsub`  | 取消每日推送订阅                  |
| `/ainews_status` | 查看推送状态与订阅信息            |
| `/ainews_retry`  | 管理员立即补发今天的早报到所有订阅目标（忽略已有推送记录） |

## ⚙️ 配置说明

安装插件后，在 AstrBot 管理面板中可配置以下选项：

| 配置项                             | 说明                                                              | 默认值 |
| ---------------------------------- | ----------------------------------------------------------------- | ------ |
| `push_hour` 每日推送时间（小时）   | 0-23，设定首次检查 RSS 的小时                                     | 8      |
| `push_minute` 每日推送时间（分钟） | 0-59，设定首次检查 RSS 的分钟                                     | 0      |
| `rss_poll_interval` RSS 轮询间隔   | 当 RSS 尚未更新当日内容时，每隔多少秒重新检查一次（默认 10 分钟） | 600    |
| `subscribed_groups` 订阅群号       | 手动填写需要推送的 QQ 群号，每行一个                              | 空     |
| `subscribed_users` 订阅 QQ 号      | 手动填写需要私聊推送的 QQ 号，每行一个                            | 空     |
| `push_platform_id` 推送平台实例 ID | 仅填群号或账号 ID 时使用；留空则选择唯一的 OneBot QQ 连接         | 空     |

推荐在实际接收推送的群或私聊中发送 `/ainews_sub`，插件会保存该会话的完整标识。手动配置也支持 `平台实例ID:账号或群号`、`平台实例ID:FriendMessage:账号ID` 和 `平台实例ID:GroupMessage:群ID`。这里的第一段是 AstrBot 平台实例 ID，可发送 `/ainews_status` 查看当前会话标识。

只有一个 OneBot QQ 连接时，直接填写 QQ 号或群号即可自动识别。存在多个 QQ 连接时，请指定 `push_platform_id` 或为每个订阅添加平台实例 ID。

如果旧版本曾出现 `cannot find platform ... message not sent` 却记录“推送成功”，更新后可由 AstrBot 管理员发送 `/ainews_retry` 补发今天这期。该命令会对所有当前订阅目标重新发送；定时重试则只处理尚未成功提交的目标。

## 📦 安装

1. 在 AstrBot 管理面板的插件页面点击「安装插件」，选择从 URL 安装。
2. 填入本仓库链接：`https://github.com/Ars1027/astrbot_plugin_daily_ai_news`。
3. 安装完成后，在目标群或私聊发送 `/ainews` 测试获取，再发送 `/ainews_sub` 订阅每日推送。

## 📌 注意事项

- **需要配置 LLM**：AI 总结功能依赖 AstrBot 中已配置的 LLM Provider，请确保至少启用了一个 LLM 服务
- 若 AI 总结失败，插件会自动回退使用原文摘要进行推送
- 插件在重启后会自动补偿检查：若已过推送时间且当天未推送，会立即尝试拉取并推送
- 配置群号方式需要填写 QQ 群号码（纯数字），指令方式需在群内发送 `/ainews_sub`
- 两种订阅方式（配置文件 + 指令）可同时使用，插件会自动合并去重
- AI 总结缓存最多保留最近 10 天的记录
- 主动推送会检查 AstrBot 的发送返回值；平台未匹配或发送抛出异常时，不会把当天记录为完成。部分目标失败时会保留成功目标的记录并重试失败目标。

## 📝 更新日志

详见 [CHANGELOG.md](CHANGELOG.md)。

## 📄 License

[GPL-3.0](LICENSE)
