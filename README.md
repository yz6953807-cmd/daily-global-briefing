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
- `.nojekyll`：告诉 GitHub Pages 按普通静态网页发布。

## 互动小兔监督员

网页内置一个原创的毒舌小兔监督员。她会在页面里移动，双击页面可开启或关闭“胡萝卜光标”吸引模式，拖拽她会挣扎吐槽；她会趁用户走神时张嘴吧唧吧唧地逐字吃掉几段文字，双击小兔本体后才会恢复。聊天面板支持本页内容匹配和公开知识源联网速查，回答后会附带一点挖苦式点评。

如果部署了 `doubao-worker/` 里的代理，并在聊天框输入 `设置豆包接口 https://你的代理地址/chat`，小兔会优先调用豆包大语言模型回答；未配置时会自动退回公开知识源兜底。

## 每天更新逻辑

每天 8:30 自动任务会先根据当天新闻主线生成一张新的主题背景图，再生成新的报告。最新版会写成 `index.html`，当天背景会写成 `images/today-bg.png`，然后一起推送到 GitHub 仓库：

https://github.com/yz6953807-cmd/daily-global-briefing

GitHub Pages 更新后，朋友继续打开同一个固定链接即可看到最新版。

## 手动推送

如果固定链接还没显示最新内容或背景图，可以双击运行：

`推送到GitHub.command`

它会自动进入正确的 GitHub 本地仓库，并推送 `index.html` 和 `images/today-bg.png`。如果 GitHub 要求输入密码，请粘贴新的 GitHub token。
