# Aurora 在阿里云 DSW 上部署

这份说明对应当前代码的推荐部署方式：

- 1 台 DSW 实例部署 `UI + API`
- 多台 DSW 实例部署 `sandbox`
- Aurora 后端通过沙箱注册表给用户分配专属沙箱
- 用户长时间 3 天不使用时自动释放绑定

## 重要前提

DSW 本身是容器化环境，实例内不支持安装或运行 Docker 守护进程。因此：

- 本地可以使用 `docker compose`
- DSW 上不要再执行 `docker build` 或 `docker run`
- DSW 生产方案应该使用 `Custom Image`

## 一、镜像准备

建议准备两类自定义镜像并推送到阿里云 ACR：

- `aurora-app`: 运行 UI + API
- `aurora-sandbox`: 运行独立沙箱

基础镜像要求：

- `python:3.13.9-cpu-ubuntu22.04`

镜像内需要满足：

- Python `3.13.9`
- Node.js `22.14.0`
- Aurora 代码与依赖

如果你先手工把环境装到一个 DSW 实例里，也可以在实例处于 `Running` 状态时使用 DSW 的 `Create Image` 能力，把实例环境保存为自定义镜像后复用。

## 二、实例规划

推荐至少创建以下实例：

- `aurora-app`
- `aurora-sandbox-01`
- `aurora-sandbox-02`

如果并发用户更多，就继续增加 `aurora-sandbox-03`、`aurora-sandbox-04`。

## 三、应用实例

用途：

- 提供 Aurora 前端
- 提供 Aurora API
- 连接 PostgreSQL / Redis

推荐配置：

- 选择你的目标 `Workspace`
- 创建 1 台 DSW 实例
- `Image config` 选择 `Custom Image`
- 选择 `aurora-app` 镜像

生产环境建议 PostgreSQL 使用 ApsaraDB RDS for PostgreSQL，Redis 使用 Tair/Redis 托管版。

UI/API 放在 DSW 实例即可，状态型中间件不要和 DSW 生命周期耦合。

如果你只是临时验证，也可以先把 PostgreSQL / Redis 装到同一台 DSW 实例里，但这不是推荐的长期方案。

## 四、沙箱实例

用途：

- 每台实例只运行一个 Aurora sandbox
- 由 Aurora API 通过注册表调度

推荐配置：

- 每个沙箱 1 台 DSW 实例
- `Image config` 选择 `Custom Image`
- 选择 `aurora-sandbox` 镜像

实例启动后，需要确认以下端口在实例内部正常监听：

- `8080`
- `9222`
- `5901`

如果希望某个用户固定连接到指定的 DSW 沙箱实例，可以在 Aurora 设置里的“专属沙箱”中直接填写该实例的 VPC 内网 IP/域名。Aurora 只会直连这个手工配置的地址；如果用户没有配置该地址，系统会提示“沙箱没有配置，沙箱不可用”，并且不会自动连接任何默认沙箱。

## 五、对外访问

Aurora 需要至少暴露这些服务：

- 应用实例 UI/API 入口
- 各沙箱实例的 `8080/9222/5901`

DSW 对外访问应使用 `Custom Service / Public Network Access` 能力完成端口暴露。生产环境如果需要公网访问，还要准备：

- NAT Gateway
- EIP
- 对应安全组放行规则

## 六、Aurora 应用实例环境变量

在 `aurora-app` 实例中，需要配置：

- `NEXT_PUBLIC_API_BASE_URL=http://<app-host>:8000/api`
- `SQLALCHEMY_DATABASE_URI=<你的 PostgreSQL 连接串>`
- `REDIS_HOST=<你的 Redis 地址>`
- `REDIS_PORT=<你的 Redis 端口>`
- `SANDBOX_MODE=registry`
- `SANDBOX_BINDING_TTL_HOURS=72`
- `SANDBOX_REGISTRY_JSON=<多个沙箱的 JSON 列表>`

示例：

```json
[
  {
    "sandbox_id": "sandbox-01",
    "label": "DSW Sandbox 01",
    "base_url": "http://<sandbox-01-host>:8080",
    "cdp_url": "http://<sandbox-01-host>:9222",
    "vnc_url": "ws://<sandbox-01-host>:5901"
  },
  {
    "sandbox_id": "sandbox-02",
    "label": "DSW Sandbox 02",
    "base_url": "http://<sandbox-02-host>:8080",
    "cdp_url": "http://<sandbox-02-host>:9222",
    "vnc_url": "ws://<sandbox-02-host>:5901"
  }
]
```

应用实例启动命令：

```bash
git clone <your-repo-url> aurora
cd aurora
./scripts/dsw-app-start.sh
```

默认会完成：

- 执行 `alembic upgrade head`
- 启动 API `:8000`
- 构建并启动 UI `:3000`

日志位置：

- `.logs/dsw/api.log`
- `.logs/dsw/ui-build.log`
- `.logs/dsw/ui.log`

## 六点五、单实例 One-Box 启动脚本

如果你选择在 1 台 DSW 实例里同时运行 `UI + API + PostgreSQL + Redis`，可直接使用：

- [scripts/dsw-app-onebox.sh](/Users/tianxiaobo/comind/aurora/scripts/dsw-app-onebox.sh)

使用前提：

- 代码已经 clone 到 DSW 实例内，例如 `/cpfs/user/fh/aurora`
- 计划将持久化数据放在代码同级目录，例如 `/cpfs/user/fh/aurora-state`
- 如果不想把 OSS 密钥写进仓库，可在代码同级目录单独放 secrets 文件，例如 `/cpfs/user/fh/.aurora-secrets.env`
- 已经在 DSW 控制台为该实例准备好 `3000` 和 `8000` 的自定义服务
- `NEXT_PUBLIC_API_BASE_URL` 必须显式传入，值应为该实例对外暴露的 API 地址，例如 `http://<api-service-host>:8000/api`

启动方式：

```bash
cd /cpfs/user/fh/aurora
chmod +x ./scripts/dsw-app-onebox.sh
NEXT_PUBLIC_API_BASE_URL=http://47.237.68.223:8013/api ./scripts/dsw-app-onebox.sh
```

可选的 secrets 文件示例：

```bash
cat > /cpfs/user/fh/.aurora-secrets.env <<'EOF'
OSS_ENDPOINT=oss-cn-shanghai-internal.aliyuncs.com
OSS_ACCESS_KEY_ID=<your-ak>
OSS_ACCESS_KEY_SECRET=<your-sk>
OSS_BUCKET_NAME=lsh-oss-agi-tool-platform
OSS_SCHEME=https
EOF
```

脚本和后端配置会自动读取这个文件；如果你想换位置，也可以在启动前显式传：

```bash
AURORA_SECRETS_FILE=/cpfs/user/fh/.aurora-secrets.env \
NEXT_PUBLIC_API_BASE_URL=http://<api-service-host>:8000/api \
./scripts/dsw-app-onebox.sh
```

脚本会自动完成：

- 安装 PostgreSQL、Redis、Node.js `22.14.0`、`uv`
- 初始化 PostgreSQL 数据目录
- 启动本机 PostgreSQL 和 Redis
- 生成根目录 `.env`（若不存在）
- `uv sync --package api --python 3.13.9`
- `alembic upgrade head`
- 构建并启动 UI
- 启动 API

默认目录：

- 代码目录：`/cpfs/user/fh/aurora`
- 数据目录：`/cpfs/user/fh/aurora-state`
- PostgreSQL 数据：`/cpfs/user/fh/aurora-state/postgres`
- Redis 数据：`/cpfs/user/fh/aurora-state/redis`
- 日志目录：`/cpfs/user/fh/aurora-state/logs`

注意：

- 不要把 PostgreSQL 或 Redis 数据目录放在 `/oss`
- 如果你已有手工维护的 `.env`，脚本会保留现有 `.env`，不会覆盖
- 首次启动会比较慢，主要耗时在 `apt-get install`、`uv sync` 和 `npm run build`

## 七、用户使用流程

部署完成后：

1. 用户输入账号登录
2. 系统自动注册，默认密码固定为 `123456`
3. 用户进入 `Aurora 设置`
4. 配置自己的 OpenAI 兼容模型密钥
5. 配置自己的 SerpAPI Key
6. 配置 DSW 沙箱地址

## 八、验证顺序

建议按这个顺序验证：

1. 打开 Aurora 首页，使用一个新账号登录
2. 打开 `Aurora 设置`，写入模型 `api_key`
3. 上传图片并提问，确认模型可直接读图
4. 写入 SerpAPI Key，确认 Google 搜索能返回结果
5. 在设置里选择某个沙箱
6. 发起任务并打开 VNC 预览，确认连接的是所选沙箱
7. 使用第二个账号登录，确认其配置与沙箱绑定互相隔离

## 九、运维建议

- DSW 的 `Custom Startup Script` 有 3 分钟超时，更适合做小型初始化，不适合安装大量依赖
- 长期稳定运行的环境尽量固化到 `Custom Image`
- 公网访问仅适合开发验证；高可用生产网关建议再加独立反向代理层
