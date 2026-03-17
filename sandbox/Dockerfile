# 1.使用Ubuntu 22.04基础镜像来源
FROM ubuntu:22.04

# 2.安装过程避免交互式提示并设置主机名
ENV DEBIAN_FRONTEND=noninteractive
ENV HOSTNAME=sandbox
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

# 3.将ubuntu默认的apt软件源地址统一换成阿里云镜像源
RUN sed -i 's|http://archive.ubuntu.com/ubuntu/|http://mirrors.aliyun.com/ubuntu/|g' /etc/apt/sources.list && \
    sed -i 's|http://security.ubuntu.com/ubuntu/|http://mirrors.aliyun.com/ubuntu/|g' /etc/apt/sources.list && \
    sed -i 's|http://ports.ubuntu.com/ubuntu-ports/|http://mirrors.aliyun.com/ubuntu-ports/|g' /etc/apt/sources.list

# 4.更新和安装基础软件后并移除依赖
RUN apt-get update && apt-get install -y \
    sudo bc curl wget gnupg software-properties-common supervisor \
    xterm socat xvfb x11vnc websockify\
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 5.创建用户ubuntu并赋予sudo权限
RUN useradd -m -d /home/ubuntu -s /bin/bash ubuntu && \
    echo "ubuntu ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ubuntu

# 6.安装Python 3.13版本
RUN add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3.13 python3.13-venv python3.13-dev && \
    python3.13 -m ensurepip --upgrade && \
    python3.13 -m pip install --no-cache-dir --upgrade pip setuptools wheel && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 7.安装 Node.js 22.14.0
RUN ARCH="$(dpkg --print-architecture)" && \
    case "$ARCH" in \
      amd64) NODE_ARCH="x64" ;; \
      arm64) NODE_ARCH="arm64" ;; \
      *) echo "Unsupported architecture: $ARCH" && exit 1 ;; \
    esac && \
    curl -fsSL "https://nodejs.org/dist/v22.14.0/node-v22.14.0-linux-${NODE_ARCH}.tar.xz" -o /tmp/node.tar.xz && \
    tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 && \
    rm /tmp/node.tar.xz

# 8.将npm镜像源设置为阿里云镜像源
RUN npm config set registry https://registry.npmmirror.com

# 9.安装Google Chrome浏览器
RUN /usr/bin/python3.10 /usr/bin/add-apt-repository ppa:xtradeb/apps -y && \
    apt-get update && \
    apt-get install -y chromium --no-install-recommends && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 10.安装中文字体和语言支持
RUN apt-get update && apt-get install -y \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    language-pack-zh-hans \
    locales \
    && locale-gen zh_CN.UTF-8 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 11.设置默认编码
ENV LANG=zh_CN.UTF-8 \
    LANGUAGE=zh_CN:zh \
    LC_ALL=zh_CN.UTF-8

# 12.设置工作空间
WORKDIR /sandbox

# 13.拷贝项目依赖文件到工作空间并安装依赖
COPY requirements.txt .
RUN python3.13 -m pip install --no-cache-dir -r requirements.txt

# 14.拷贝当前整个项目文件
COPY . .

# 15.将supervisord.conf拷贝至supervisor服务配置目录中
COPY supervisord.conf /etc/supervisor/conf.d/sandbox.conf

# 16.暴露端口: 8080(FastAPI) 9222(CDP) 5900(vnc)
EXPOSE 8080 9222 5900 5901

# 17.额外的环境变量配置
ENV CHROME_ARGS=""
ENV UVI_ARGS=""

# 18.使用supervisor管理所有进程
CMD ["/usr/bin/supervisord", "-n", "-c", "/sandbox/supervisord.conf"]
