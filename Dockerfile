FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt /root/

# 安装Python依赖
RUN pip install --no-cache-dir -r /root/requirements.txt  -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制应用代码
COPY . /root/

# 暴露端口
EXPOSE 5000

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV TIMEZONE=Asia/Shanghai

# 启动应用
CMD ["python", "/root/app.py"]

