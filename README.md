# 轻量级定时任务服务

一个极简、高效、资源占用极低的定时任务管理系统，使用 Python + Flask + APScheduler 构建，支持 Docker 容器化部署。

## ✨ 特性

- 🚀 **极低资源占用**：仅依赖 Flask、APScheduler 和 pytz 三个核心库
- ⏰ **多种调度方式**：支持 Cron 表达式、每日定时、循环执行
- 🎨 **现代化界面**：美观的渐变设计，支持列表视图和按钮视图切换
- 📝 **完整日志**：记录每次任务执行的输出、错误、状态和执行时长
- 🔧 **简单易用**：Web 界面直观，支持任务创建、编辑、删除、启用/禁用、立即执行
- 💾 **轻量数据库**：使用 SQLite，无需额外数据库服务
- 🐳 **容器化部署**：提供完整的 Docker 和 Docker Compose 配置
- 🌍 **时区支持**：可自定义时区配置，默认 Asia/Shanghai

## 📋 系统要求

- Python 3.7+
- Linux/Unix 系统（使用 bash 执行命令）
- 最低内存需求: ~50MB
- 最低 CPU 需求: 单核即可

## 🚀 快速开始

### 方式一：直接运行（推荐用于开发）

#### 1. 安装依赖

```bash
pip install -r requirements.txt
```

#### 2. 启动服务

```bash
python app.py
```

#### 3. 访问 Web 界面

打开浏览器访问: http://localhost:5000

### 方式二：Docker 部署（推荐用于生产）

#### 使用 Docker Compose（推荐）

```bash
# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

#### 使用 Docker

```bash
# 构建镜像
docker build -t task-scheduler .

# 运行容器
docker run -d \
  --name task-scheduler \
  -p 5000:5000 \
  -v $(pwd):/app/ \
  -e TIMEZONE=Asia/Shanghai \
  task-scheduler

# 查看日志
docker logs -f task-scheduler

# 停止容器
docker stop task-scheduler
docker rm task-scheduler
```

## 📖 使用说明

### 创建任务

1. 点击"创建新任务"按钮
2. 填写任务信息：
   - **任务名称**：给任务起一个有意义的名字
   - **执行命令**：要执行的 bash 命令或脚本路径
   - **调度类型**：选择一种调度方式
   - **启用状态**：是否立即启用任务

### 调度类型说明

#### 1. Cron 表达式

使用标准的 Cron 语法（5 段式）：

```
分 时 日 月 星期

示例:
0 2 * * *        # 每天凌晨2点
*/30 * * * *     # 每30分钟
0 9-18 * * 1-5   # 工作日的9点到18点每小时执行
```

#### 2. 每天定时

指定每天固定时间执行，例如每天凌晨2点、每天下午3点等。

#### 3. 循环执行

按固定间隔重复执行，支持：
- 秒级循环（如每 30 秒）
- 分钟级循环（如每 5 分钟）
- 小时级循环（如每 2 小时）

### 任务管理

- **立即执行**：点击"立即执行"按钮可手动触发任务
- **编辑任务**：修改任务配置
- **删除任务**：永久删除任务及相关日志
- **启用/禁用**：临时禁用任务而不删除
- **查看下次执行时间**：任务列表显示下次计划执行时间

### 视图模式

支持两种视图模式：
- **列表视图**：以表格形式展示任务，信息更全面
- **按钮视图**：以卡片形式展示任务，便于快速执行

### 日志查询

在"执行日志"标签页中：
- 查看所有任务的执行历史
- 按任务筛选日志
- 查看命令输出和错误信息
- 查看执行状态（成功/失败）和执行时长
- 点击日志查看详细信息
- 清空历史日志

## 💡 使用示例

### 示例 1: 每天备份数据库

- **任务名称**：数据库备份
- **执行命令**：`/usr/bin/mysqldump -u root -ppassword mydb > /backup/mydb_$(date +\%Y\%m\%d).sql`
- **调度类型**：每天定时
- **时间**：02:00

### 示例 2: 每小时清理临时文件

- **任务名称**：清理临时文件
- **执行命令**：`find /tmp -type f -mtime +7 -delete`
- **调度类型**：Cron 表达式
- **表达式**：`0 * * * *`

### 示例 3: 每 5 分钟检查服务状态

- **任务名称**：服务健康检查
- **执行命令**：`/path/to/health_check.sh`
- **调度类型**：循环执行
- **间隔**：300 秒（5 分钟）

### 示例 4: 每 30 秒采集系统指标

- **任务名称**：系统监控
- **执行命令**：`top -b -n 1 | head -20 >> /var/log/system_metrics.log`
- **调度类型**：循环执行
- **间隔**：30 秒

## 🗂️ 文件结构

```
.
├── app.py                 # 主应用程序
├── requirements.txt       # Python 依赖
├── Dockerfile            # Docker 镜像构建文件
├── docker-compose.yml    # Docker Compose 配置
├── tasks.db              # SQLite 数据库（自动创建）
├── templates/
│   ├── index.html        # 主界面模板
│   └── log_detail.html   # 日志详情页模板
└── README.md             # 项目文档
```

## 🔧 配置说明

### 时区配置

通过环境变量 `TIMEZONE` 配置时区（默认为 `Asia/Shanghai`）：

```bash
# 直接运行时设置时区
TIMEZONE=America/New_York python app.py

# Docker 运行时设置时区
docker run -d \
  -e TIMEZONE=America/New_York \
  -p 5000:5000 \
  task-scheduler

# Docker Compose 中修改 docker-compose.yml
environment:
  - TIMEZONE=America/New_York
```

常用时区列表：
- `Asia/Shanghai` - 中国上海（东八区）
- `Asia/Tokyo` - 日本东京
- `America/New_York` - 美国纽约
- `America/Los_Angeles` - 美国洛杉矶
- `Europe/London` - 英国伦敦
- `UTC` - 协调世界时

更多时区请参考：[pytz 时区列表](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)

### 应用配置

在 `app.py` 中可以修改以下配置：

```python
TASKS_DB_PATH = 'tasks.db'     # 数据库文件路径
TIMEZONE = 'Asia/Shanghai'     # 时区（也可通过环境变量设置）
app.run(host='0.0.0.0',        # 监听地址
        port=5000,             # 监听端口
        debug=False)           # 调试模式
```

### 任务超时配置

默认任务执行超时时间为 1 小时（3600 秒），可在 `app.py` 的 `execute_task` 函数中修改：

```python
result = subprocess.run(
    command,
    shell=True,
    executable='/bin/bash',
    capture_output=True,
    text=True,
    timeout=3600  # 修改此值调整超时时间（秒）
)
```

## 💾 数据库说明

系统使用单个 SQLite 数据库文件（`tasks.db`）存储所有数据：

### 数据表结构

#### tasks 表（任务配置）
- `id`：任务 ID（自增主键）
- `name`：任务名称
- `command`：执行命令
- `schedule_type`：调度类型（cron/daily/interval）
- `schedule_config`：调度配置（JSON 格式）
- `enabled`：是否启用（0/1）
- `created_at`：创建时间
- `updated_at`：更新时间

#### task_logs 表（执行日志）
- `id`：日志 ID（自增主键）
- `task_id`：关联的任务 ID
- `task_name`：任务名称
- `command`：执行的命令
- `output`：标准输出
- `error`：标准错误
- `exit_code`：退出码
- `started_at`：开始时间
- `finished_at`：结束时间

#### settings 表（系统设置）
- `key`：配置键
- `value`：配置值
- `updated_at`：更新时间

## 🔌 API 接口

系统提供 RESTful API 接口：

### 任务管理
- `GET /api/tasks` - 获取所有任务
- `POST /api/tasks` - 创建任务
- `PUT /api/tasks/<task_id>` - 更新任务
- `DELETE /api/tasks/<task_id>` - 删除任务
- `POST /api/tasks/<task_id>/run` - 立即执行任务

### 日志管理
- `GET /api/logs?task_id=<id>&limit=<num>` - 获取日志
- `DELETE /api/logs/<log_id>` - 删除日志
- `POST /api/logs/clear?task_id=<id>` - 清空日志

### 设置管理
- `GET /api/settings/view_mode` - 获取视图模式
- `POST /api/settings/view_mode` - 设置视图模式

## 🛡️ 安全建议

1. **生产环境部署**：建议使用反向代理（如 Nginx）并配置 HTTPS
2. **访问控制**：建议添加身份认证机制，限制访问权限
3. **命令安全**：谨慎配置任务命令，避免执行不受信任的代码
4. **资源限制**：建议在 Docker 中设置资源限制（内存、CPU）
5. **日志管理**：定期清理历史日志，避免数据库过大

## 📝 依赖说明

```
Flask==3.0.0        # Web 框架
APScheduler==3.10.4 # 任务调度器
pytz==2024.1        # 时区支持
```

## 🐛 故障排查

### 任务未执行
1. 检查任务是否已启用
2. 查看调度配置是否正确
3. 检查系统日志是否有错误信息

### 任务执行失败
1. 查看执行日志中的错误信息
2. 确认命令路径和权限是否正确
3. 检查是否超时（默认 1 小时）

### 时区不正确
1. 检查环境变量 `TIMEZONE` 是否设置正确
2. 重启服务使时区配置生效

## 📄 许可证

本项目采用 MIT 许可证。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📧 联系方式

如有问题或建议，欢迎通过 Issue 反馈。

