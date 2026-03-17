# Aurora

Aurora 是一个面向多用户的 AI Agent 平台，支持本地开发和阿里云 DSW 部署。当前版本完成了这些核心改造：

- 本地运行统一到 `Python 3.13.9` 和 `Node.js 22.14.0`
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

启动命令：

```bash
./scripts/dev-up.sh
```

本地开发模式下：

- Docker 只负责启动 PostgreSQL、Redis、Sandbox
- API 使用本机 `uv` 启动
- UI 使用本机 `npm` 启动
- 默认直接读取 [`.env.example`](/Users/tianxiaobo/comind/aurora/.env.example)，不需要先复制 `.env`
- `Ctrl+C` 会直接停止本地 API、UI 和基础设施

生产环境默认读取 `.env`。

完整本地调试步骤见：

- [docs/local-development.md](/Users/tianxiaobo/comind/aurora/docs/local-development.md)

默认访问地址：

- UI: `http://localhost:3000`
- API: `http://localhost:8000/api`

停止命令：

```bash
./scripts/dev-down.sh
```

## 默认行为

- 首次输入账号登录时会自动注册
- 默认密码固定为 `123456`
- 系统不内置用户级 LLM / SerpAPI 密钥
- 用户首次登录后，通过右上角 `Aurora 设置` 配置：
  - OpenAI 兼容 `base_url`
  - `api_key`
  - 默认模型 `gpt-5.4`
  - SerpAPI Key
  - 优先沙箱

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
- 用户选择专属沙箱
- 3 天闲置自动释放绑定
