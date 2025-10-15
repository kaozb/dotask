FROM python:3.11-slim AS builder

# 安装必要的工具
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        procps \
        curl \
        wget \
        ncat \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*


# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt /root/

# 安装Python依赖，使用清华源
RUN pip config set global.index-url https://mirrors.pku.edu.cn/pypi/web/simple && pip install --no-cache-dir -r /root/requirements.txt

# 复制应用代码
COPY . /root/

# 暴露端口
EXPOSE 5000

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV TIMEZONE=Asia/Shanghai

# 启动应用
CMD ["python", "/root/app.py"]