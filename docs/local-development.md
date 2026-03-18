# Aurora 本地开发与调试

本文档对应当前仓库的本地开发方式。

## 1. 前置条件

本地需要先准备：

- Docker Desktop 或可用的 Docker Engine
- Docker Compose
- Python `3.13.9`
- `uv`
- Node.js `22.14.0`
- `npm`

版本声明文件：

- [`.python-version`](/Users/tianxiaobo/comind/aurora/.python-version)
- [`.nvmrc`](/Users/tianxiaobo/comind/aurora/.nvmrc)

说明：

- 本地开发默认读取 [`.env.example`](/Users/tianxiaobo/comind/aurora/.env.example)
- 生产环境默认读取 `.env`
- 本地调试时不需要先复制 `.env`

## 2. 一键启动

在项目根目录执行：

```bash
cd /Users/tianxiaobo/comind/aurora
./scripts/dev-up.sh
```

如需只启动不跟日志：

```bash
./scripts/dev-up.sh --no-follow-logs
```

这个脚本会：

- 使用 `.env.example` 作为本地环境变量文件
- 使用 Docker 启动 PostgreSQL、Redis、Sandbox
- 使用 `uv` 同步并启动本地 API
- 使用 `npm` 启动本地 UI
- 将本地开发日志写入 `.logs/dev`
- 本地 Docker 资源会使用独立的 compose project / volume / network，避免和你机器上的旧 `aurora_*` 资源冲突
- 启动前会自动清理占用 `3000` 和 `8000` 端口的旧本地开发进程
- sandbox 镜像会按 `sandbox/` 目录内容自动判定是否需要重建，避免代码改了但仍复用旧镜像
- 本地 API 以单进程模式启动，优先保证稳定可调试
- sandbox 会通过 `http://127.0.0.1:8080/api/supervisor/status` 做健康检查，启动失败时脚本会直接报错退出

说明：

- `./scripts/dev-up.sh` 会在后台启动本地 API 和 UI
- 默认会在当前窗口持续跟随 API、UI 和基础设施日志
- 如需只启动不跟日志，使用 `./scripts/dev-up.sh --no-follow-logs`
- 默认模式下按 `Ctrl+C` 会直接停止本地 API、UI 和 Docker 基础设施

默认访问地址：

- UI: `http://localhost:3000`
- API: `http://localhost:8000/api`
- API Docs: `http://localhost:8000/docs`

## 3. 首次登录与基础配置

启动完成后，打开浏览器访问：

```text
http://localhost:3000
```

登录方式：

- 用户名：任意新账号
- 密码：`123456`

系统会在首次登录时自动注册该账号。

登录后，打开右上角 `Aurora 设置`，至少补齐以下配置：

- `base_url`: `https://codex.ysaikeji.cn/v1`
- `model_name`: `gpt-5.4`
- `api_key`: 你自己的模型密钥
- `SerpAPI Key`: 你自己的 Google 搜索密钥
- `DSW 沙箱地址`: 本地联调时填写 `127.0.0.1`

说明：

- 不填 `api_key` 时，页面可以打开，但模型调用会失败
- 不填 `SerpAPI Key` 时，Google 搜索功能不可用
- 不填 `DSW 沙箱地址` 时，系统会提示“沙箱没有配置，沙箱不可用”，并且不会自动连接本地 sandbox

## 4. 推荐调试顺序

建议按这个顺序验证：

1. 首页能打开，登录成功。
2. 发送一条普通文本消息，确认模型可以返回结果。
3. 上传一张图片并提问，确认模型可以读图。
4. 配置 SerpAPI Key 后测试搜索。
5. 发起需要沙箱的任务，确认页面能正常打开 VNC 预览。

## 5. 常用调试命令

查看基础设施容器状态：

```bash
docker compose ps
```

查看 API 日志：

```bash
tail -f .logs/dev/api.log
```

查看 UI 日志：

```bash
tail -f .logs/dev/ui.log
```

查看 Sandbox 日志：

```bash
docker compose logs -f aurora-sandbox
```

停止本地环境：

- 执行 `./scripts/dev-down.sh`

如果需要重新启动：

```bash
./scripts/dev-up.sh
```

## 6. 本地环境文件规则

当前规则如下：

- 本地 `./scripts/dev-up.sh` 强制使用 `.env.example`
- 本地 API/UI 直接跑在宿主机上
- Docker 只负责 PostgreSQL、Redis、Sandbox
- 后端和 sandbox 在 `ENV!=production` 时默认读取根目录 `.env.example`
- 生产环境在 `ENV=production` 时默认读取根目录 `.env`

因此：

- 本地调试时，修改 [`.env.example`](/Users/tianxiaobo/comind/aurora/.env.example)
- 生产部署时，提供 `.env`

## 7. 常见问题

### 7.1 页面能打开，但对话失败

优先检查：

- 是否已经在 `Aurora 设置` 中填写 `api_key`
- `tail -f .logs/dev/api.log` 中是否有上游模型报错

### 7.2 搜索功能失败

优先检查：

- 是否已经填写 SerpAPI Key
- 返回错误是否为上游接口鉴权失败

### 7.3 图片上传成功，但模型无法读图

优先检查：

- OSS 配置是否正确
- API 日志中是否生成了签名图片链接
- 上游 OpenAI 兼容接口是否支持图片输入

### 7.4 沙箱相关任务失败

优先检查：

- `aurora-sandbox` 容器是否正常启动
- `docker compose logs -f aurora-sandbox`
- `.env.example` 中的 `SANDBOX_ADDRESS` 是否为 `localhost`

### 7.5 端口被占用

如果 `3000`、`5432`、`6379`、`8000`、`8080`、`9222` 或 `5901` 被占用，先释放端口，或按需修改本地脚本/Compose 端口映射后重新执行：

```bash
./scripts/dev-down.sh
./scripts/dev-up.sh
```
