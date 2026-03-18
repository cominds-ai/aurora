# 1.使用与本地/DSW 更接近的 Ubuntu 22.04 基础镜像
FROM ubuntu:22.04

# 2.避免交互式安装
ENV DEBIAN_FRONTEND=noninteractive
ENV UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PYTHONPATH=/workspace/api
ENV PYTHONUNBUFFERED=1
ENV PATH=/workspace/.venv/bin:$PATH

# 3.配置容器工作空间
WORKDIR /workspace

# 4.切换 Ubuntu 软件源到阿里云并安装 Python 3.13 与基础工具
RUN sed -i 's|http://archive.ubuntu.com/ubuntu/|http://mirrors.aliyun.com/ubuntu/|g' /etc/apt/sources.list && \
    sed -i 's|http://security.ubuntu.com/ubuntu/|http://mirrors.aliyun.com/ubuntu/|g' /etc/apt/sources.list && \
    sed -i 's|http://ports.ubuntu.com/ubuntu-ports/|http://mirrors.aliyun.com/ubuntu-ports/|g' /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends curl xz-utils gnupg software-properties-common ca-certificates && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y --no-install-recommends python3.13 python3.13-venv python3.13-dev && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.13 1 && \
    python3.13 -m ensurepip --upgrade && \
    python3.13 -m pip install --no-cache-dir --upgrade pip setuptools wheel uv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 5.安装 Node.js 22.14.0
RUN ARCH="$(dpkg --print-architecture)" && \
    case "$ARCH" in \
      amd64) NODE_ARCH="x64" ;; \
      arm64) NODE_ARCH="arm64" ;; \
      *) echo "Unsupported architecture: $ARCH" && exit 1 ;; \
    esac && \
    curl -fsSL "https://nodejs.org/dist/v22.14.0/node-v22.14.0-linux-${NODE_ARCH}.tar.xz" -o /tmp/node.tar.xz && \
    tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 && \
    rm /tmp/node.tar.xz

# 6.拷贝项目文件并通过根级 uv workspace 安装依赖
COPY . .
RUN uv sync --package api --python 3.13.9 --no-dev

# 7.为运行脚本配置权限
RUN chmod +x api/run.sh

# 8.暴露端口号
EXPOSE 8000

# 9.启动命令脚本
CMD ["./api/run.sh"]
