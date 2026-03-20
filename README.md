# Aurora

Aurora 是一个面向多用户的 AI Agent 平台，支持本地开发和阿里云 DSW 部署。当前版本完成了这些核心改造：

- 仓库已完成 monorepo 工程化：Node workspace + Python `uv workspace`
- 本地运行统一到 `Python 3.13.9` 和 `Node.js 22.14.0`
- Python 依赖、Docker 构建和 DSW 脚本都统一收口到根级 `uv workspace`
- 品牌命名统一为 `Aurora`，界面默认用户称呼改为“地球人”
- 对象存储切换为阿里云 OSS
- 默认模型切换为 OpenAI 兼容接口，默认模型为 `gpt-5.4`
- 搜索切换为 `SerpAPI + Google`
- 增加登录、自动注册、多用户配置和用户级沙箱绑定
- 增加 DSW 单独部署 UI/API 与多沙箱注册方案

## 本地一键启动

前置要求：

- Docker / Docker Compose
- Python `3.13.9` + `uv`
- Node.js `22.14.0` + `npm`

版本声明文件已经提供：

- [`.python-version`](/Users/tianxiaobo/comind/aurora/.python-version)
- [`.nvmrc`](/Users/tianxiaobo/comind/aurora/.nvmrc)

推荐先同步 monorepo 依赖：

```bash
npm run bootstrap
```

首次执行后会在仓库根目录生成或更新 `uv.lock`，作为 Python workspace 的统一锁文件。
Node workspace 的统一锁文件为 [package-lock.json](/Users/tianxiaobo/comind/aurora/package-lock.json)。

启动命令：

```bash
npm run dev
```

本地开发模式下：

- Docker 只负责启动 PostgreSQL、Redis、Sandbox
- API 使用根级 `uv workspace` 启动，并开启 `reload`
- UI 使用根级 Node workspace 启动，并保持 Next.js 热更新
- Sandbox 使用开发期 compose override 挂载源码，并开启 `reload`
- 默认直接读取 [`.env.example`](/Users/tianxiaobo/comind/aurora/.env.example)，不需要先复制 `.env`
- 默认会在当前窗口持续输出日志
- 如需只启动不跟日志，使用 `npm run dev:detach`
- 停止本地服务使用 `npm run dev:down`

生产环境默认读取 `.env`。

完整本地调试步骤见：

- [docs/local-development.md](/Users/tianxiaobo/comind/aurora/docs/local-development.md)

默认访问地址：

- UI: `http://localhost:3000`
- API: `http://localhost:8000/api`

停止命令：

```bash
npm run dev:down
```

## 默认行为

- 首次输入账号登录时会自动注册
- 默认密码固定为 `123456`
- 系统默认内置两个模型提供商：
  - `官方默认gpt`
  - `官方默认claude`
- 用户首次登录后，通过右上角 `Aurora 设置` 配置：
  - 多个模型提供商及当前激活 provider
  - provider 对应的 `base_url`
  - provider 对应的 `api_key`
  - provider 对应的 `model_name`
  - SerpAPI Key
  - DSW 沙箱地址

两个内置 provider 的 API Key 默认从代码同级目录的 `.aurora-secrets.env` 读取：

- `AURORA_OFFICIAL_DEFAULT_GPT_API_KEY`
- `AURORA_OFFICIAL_DEFAULT_CLAUDE_API_KEY`

## 系统级配置

后端系统级配置位于 [api/core/config.py](/Users/tianxiaobo/comind/aurora/api/core/config.py)。

当前 OSS 默认值已经写入配置：

- `endpoint=oss-cn-shanghai-internal.aliyuncs.com`
- `bucket=lsh-oss-agi-tool-platform`

## DSW 部署

完整部署说明见：

- [docs/dsw-deploy.md](/Users/tianxiaobo/comind/aurora/docs/dsw-deploy.md)

如果你当前采用的是“1 台 DSW 同时运行 UI + API + PostgreSQL + Redis”的 one-box 方案，可直接使用：

- [scripts/dsw-app-onebox.sh](/Users/tianxiaobo/comind/aurora/scripts/dsw-app-onebox.sh)

其中包含：

- UI/API 合并部署到一台 DSW 实例
- 多个沙箱实例注册到 Aurora
- 用户手工配置专属沙箱地址
- 3 天闲置自动释放绑定
