# 每日简报发布文件夹

这个文件夹按文件后缀和用途整理每日全球资讯简报。

## 给朋友看的固定链接

朋友每天直接打开这个链接即可：

https://yz6953807-cmd.github.io/daily-global-briefing/

这个链接显示的是 GitHub Pages 仓库根目录的 `index.html`。每天自动更新时，会替换这个文件。

## 文件结构

- `index.html`：发布到 GitHub Pages 根目录的最新网页，固定链接会显示它；它会引用 `images/today-bg.png` 作为背景。
- `github-pages-root/`：只放 GitHub Pages 根目录需要的文件，主要是 `index.html`、`.nojekyll` 和 `images/`。
- `html/`：每日 HTML 归档文件。
- `markdown/`：每日 Markdown 归档文件。
- `images/`：每日主题背景图和图片资产，其中 `today-bg.png` 是固定链接当前使用的背景，`YYYY-MM-DD-bg.png` 是日期归档背景。
- `doubao-worker/`：小兔连接豆包大语言模型的后端代理模板，API Key 只放在代理服务端，不写进公开网页。
- `部署豆包代理.command`：双击运行后，会引导输入豆包模型 ID、Cloudflare 登录、保存 API Key secret 并部署代理。
- `.nojekyll`：告诉 GitHub Pages 按普通静态网页发布。

## 互动小兔监督员

网页内置一个原创的毒舌小兔监督员。她会在页面里移动，双击页面可开启或关闭“胡萝卜光标”吸引模式，拖拽她会挣扎吐槽；她会趁用户走神时张嘴吧唧吧唧地逐字吃掉几段文字，双击小兔本体后才会恢复。聊天面板支持本页内容匹配和公开知识源联网速查，回答后会附带一点挖苦式点评。

如果部署了 `doubao-worker/` 里的代理，并在聊天框输入 `设置豆包接口 https://你的代理地址/chat`，小兔会优先调用豆包大语言模型回答；未配置时会自动退回公开知识源兜底。

如果需要部署代理，可以双击 `部署豆包代理.command`。注意：如果火山方舟提示 API Key 不存在或未授权，需要先在方舟控制台重新生成有效 Key，并复制模型 ID 或接入点 ID。

## 每天更新逻辑

GitHub Actions 云端任务每天会在北京时间 08:20、08:50、10:30 多次尝试自动更新，避免单次定时任务被 GitHub 队列延迟或跳过。任务会抓取公开来源、生成新的报告，把最新版写成 `index.html`，把当天数据写入 `data/latest-news.json` 和 `data/YYYY-MM-DD-news.json`，并把运行状态写入 `data/status.json`。当天背景继续使用 `images/today-bg.png`，并保留日期归档图。

https://github.com/yz6953807-cmd/daily-global-briefing

GitHub Pages 更新后，朋友继续打开同一个固定链接即可看到最新版。

如果固定链接看起来没有变，先打开 `data/status.json` 或页面底部的“云端更新时间”。它们会显示最近一次云端任务的北京时间、运行编号和生成日期。

## 手动推送

如果固定链接还没显示最新内容或背景图，可以双击运行：

`推送到GitHub.command`

它会自动进入正确的 GitHub 本地仓库，并推送 `index.html` 和 `images/today-bg.png`。如果 GitHub 要求输入密码，请粘贴新的 GitHub token。
