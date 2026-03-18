# Aurora 沙箱服务

基于 Ubuntu 22.04 构建的沙箱环境，提供隔离的代码执行、浏览器自动化和远程桌面访问能力。

## 技术栈

- Ubuntu 22.04
- Python 3.13.9 + FastAPI
- Node.js 22.14.0
- Chromium (浏览器自动化)
- Xvfb + x11vnc + websockify (虚拟显示 + VNC)
- Supervisor (进程管理)

## 内置运行时依赖

当前 sandbox 镜像会预装一组常用 Python / Node 数据处理依赖，包括：

- Python：`pandas`、`openpyxl`、`xlsxwriter`、`requests`、`httpx`、`pydantic`、`PyYAML`、`python-dotenv`、`orjson`、`numpy`、`polars`、`pyarrow`、`pdfplumber`、`pypdf`、`python-docx`、`python-pptx`、`beautifulsoup4`、`lxml`、`Pillow`、`jieba`
- Node.js：`fs-extra`、`fast-glob`、`axios`、`form-data`、`xlsx`、`exceljs`、`papaparse`、`csv-parse`、`csv-stringify`、`js-yaml`、`dotenv`、`zod`、`lodash`、`dayjs`、`sharp`、`pdf-parse`、`pdf-lib`、`mammoth`、`cheerio`、`xml2js`

Node 依赖会安装在 `sandbox/node_modules`，并通过 `NODE_PATH` 暴露给沙箱内执行的 Node 脚本。

## 资源建议

仅仅“内置这些包”本身，主要增加的是镜像体积、构建时间和磁盘占用，空闲态 CPU / 内存不会线性上涨太多；真正需要调资源的是实际运行这些库时的峰值负载。

建议按单个 sandbox 容器做两档规划：

- 常规交互型任务：`2 vCPU / 4 GiB RAM`
- 高频 Excel / PDF / 表格聚合 / Arrow / 图片处理：`4 vCPU / 8 GiB RAM`

如果你的场景经常同时出现以下任务，建议直接按高配档规划：

- `pandas` / `polars` / `pyarrow` 处理大表
- `pdfplumber` / `pypdf` 批量解析 PDF
- `python-docx` / `python-pptx` 批量抽取 Office 文档
- `sharp` 批量处理图片
- 同时保留 Chromium、VNC 和数据处理任务并发运行

承载这些 sandbox 容器的宿主机，建议在总需求之上再留 `20%~30%` 的内存和 CPU 余量，避免多容器同时跑数据任务时把机器打满。

## 架构

沙箱通过 Supervisor 管理多个进程：

| 进程 | 端口 | 说明 |
|------|------|------|
| FastAPI | 8080 | REST API（文件操作、Shell 执行） |
| Chrome | 8222 (内部) | 浏览器实例 |
| socat | 9222 | Chrome DevTools Protocol 代理 |
| Xvfb | - | 虚拟显示器 (:1) |
| x11vnc | 5900 | VNC 服务 |
| websockify | 5901 | WebSocket VNC 代理 |

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/file/read-file` | 读取文件 |
| POST | `/api/file/write-file` | 写入文件 |
| POST | `/api/file/upload-file` | 上传文件 |
| GET | `/api/file/download-file` | 下载文件 |
| POST | `/api/shell/exec-command` | 执行命令 |
| POST | `/api/shell/read-shell-output` | 读取 Shell 输出 |
| GET | `/api/supervisor/status` | 获取进程状态 |

## 本地开发

### 使用开发容器

```bash
cd .devops
docker compose up -d

# SSH 连接到开发容器
ssh root@localhost -p 2222
# 密码: root
```

### 启动服务

在容器内或本地：

```bash
# 在仓库根目录同步 monorepo Python workspace
cd /Users/tianxiaobo/comind/aurora
uv sync --all-packages --python 3.13.9

# 启动 API 服务
uv run --package sandbox --python 3.13.9 uvicorn app.main:app --app-dir /Users/tianxiaobo/comind/aurora/sandbox --host 0.0.0.0 --port 8080 --reload
```

## Docker 部署

沙箱服务通过根目录的 `docker-compose.yml` 统一部署。生产环境中沙箱作为固定容器运行，API 服务通过 `SANDBOX_ADDRESS=aurora-sandbox` 连接。

### 端口说明

在 Docker Compose 部署中，沙箱端口仅在容器网络内部可访问，不对外暴露：

- `8080` - FastAPI REST API
- `9222` - Chrome DevTools Protocol
- `5900` - VNC RFB
- `5901` - WebSocket VNC（API 服务通过此端口代理 VNC 到前端）
