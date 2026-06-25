# 稳定更新机制说明

这个仓库现在有两套更新方式：

1. GitHub 云端自动更新
   - 文件：`.github/workflows/daily-briefing.yml`
   - 时间：每天北京时间 8:30
   - 作用：在 GitHub 云端抓取公开来源，生成 `index.html`，并自动提交到仓库。
   - 优点：不依赖本地电脑是否开机。

2. 本地 Codex 自动任务
   - 仍可作为备用，但不再是唯一更新来源。

## 如果当天没有更新，先看这里

打开 GitHub 仓库：

`https://github.com/yz6953807-cmd/daily-global-briefing`

进入 `Actions`，点 `Daily global briefing update`：

- 绿色：当天云端任务成功。
- 红色：任务失败，点进去可以看失败原因。
- 没有当天记录：GitHub Actions 可能没启用，或者仓库 Actions 权限被关掉。

## 手动立即更新

在 GitHub 仓库页面：

1. 点 `Actions`
2. 点左侧 `Daily global briefing update`
3. 点右侧 `Run workflow`
4. 再点绿色 `Run workflow`

它会马上生成一次新版网页。

## 让内容更专业

当前脚本没有密钥也能更新，但会更像“公开来源摘要”。如果要让内容更像深度早报，需要把豆包/火山方舟密钥放进 GitHub Secret：

1. 仓库点 `Settings`
2. 左侧点 `Secrets and variables`
3. 点 `Actions`
4. 点 `New repository secret`
5. 添加：
   - `ARK_API_KEY`：你的火山方舟/豆包 API Key
   - `ARK_MODEL`：你的模型或接入点 ID

不要把 API Key 写进 `index.html`、README 或任何公开文件。

## GitHub 权限检查

如果任务能运行但不能提交，请检查：

1. 仓库 `Settings`
2. `Actions`
3. `General`
4. `Workflow permissions`
5. 选择 `Read and write permissions`

这个权限允许 GitHub 云端任务把新日报提交回仓库。
