# 小兔豆包代理

这个文件夹用于把网页里的小兔聊天接到豆包大语言模型。

重要：不要把豆包 API Key 写进 `index.html`。你的 GitHub Pages 网站是公开网页，任何人都能看到前端代码。API Key 必须放在后端代理的环境变量里。

## 需要准备

1. 火山方舟 / 豆包 API Key。
2. 火山方舟里的模型 ID 或接入点 ID，填到 `ARK_MODEL`。
3. 一个后端代理。这里给的是 Cloudflare Worker 模板。

## 部署思路

1. 把 `wrangler.toml.example` 复制成 `wrangler.toml`。
2. 把 `ARK_MODEL` 改成你在火山方舟控制台里使用的豆包模型或接入点 ID。
3. 用 Cloudflare Wrangler 登录并部署 Worker。
4. 用 secret 保存 API Key：

```bash
wrangler secret put ARK_API_KEY
```

5. 部署成功后，你会得到一个类似这样的地址：

```text
https://daily-briefing-doubao.你的账号.workers.dev
```

6. 在网页小兔聊天框里输入：

```text
设置豆包接口 https://daily-briefing-doubao.你的账号.workers.dev/chat
```

设置后，小兔回答会优先调用豆包；如果代理失败，会退回本页搜索和公开知识源兜底。

## 关闭豆包

在小兔聊天框里输入：

```text
关闭豆包接口
```

她会清除当前浏览器里保存的代理地址。
