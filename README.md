# 朱雀

极简、高效的定时任务管理系统，Python + Flask + APScheduler 构建，支持 Docker 部署。
效果图
![](https://wework.qpic.cn/wwpic3az/273134_-eWZgPJsS7OxVHj_1761642911)
## ✨ 核心特性

- 🚀 **极低资源占用** - 仅依赖 Flask、APScheduler、pytz 三个库，内存占用 ~50MB
- ⏰ **多种调度方式** - Cron 表达式、每日定时、循环执行
- 📺 **实时日志窗口** - 右下角浮动窗口，支持拖动/最小化/最大化
- ⚡ **快速执行命令** - 一键执行临时命令，无需创建任务
- 🔄 **运行中任务管理** - 查看和强制终止正在执行的任务
- ⚙️ **灵活配置** - 可配置日志显示和任务超时（60秒~24小时）
- 🎨 **现代化界面** - 渐变设计，列表/按钮视图切换
- 💾 **轻量数据库** - SQLite，无需额外服务
- 🐳 **容器化部署** - Docker / Docker Compose
- 🌍 **时区支持** - 默认 Asia/Shanghai

## 📋 系统要求

- Python 3.7+
- Linux/Unix 系统（bash）
- 内存：~50MB | CPU：单核

## 🚀 快速开始

### 方式一：直接运行

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python app.py

# 访问 Web 界面
# http://localhost:5000
```

### 方式二：Docker Compose（推荐）

```bash
# 启动
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止
docker-compose down
```

### 方式三：Docker

```bash
# 构建并运行
docker build -t task-scheduler .
docker run -d --name task-scheduler -p 5000:5000 -v $(pwd):/app/ task-scheduler
```

## 📖 使用说明

### 创建任务

1. 点击"创建新任务"
2. 填写任务名称、执行命令、选择调度类型

### 调度类型

**Cron 表达式**（分 时 日 月 星期）：
```
0 2 * * *        # 每天凌晨2点
*/30 * * * *     # 每30分钟
0 9-18 * * 1-5   # 工作日9-18点每小时
```

**每天定时**：每天固定时间执行

**循环执行**：按固定间隔执行（秒/分钟/小时）

### 任务操作

- **立即执行** - 手动触发，自动弹出实时日志窗口
- **编辑/删除** - 修改或永久删除任务
- **启用/禁用** - 临时禁用任务

### ✨ 实时日志窗口

**窗口控制**：
- 最小化（`-`）/ 最大化（`□`）/ 关闭（`×`）
- 可拖动标题栏移动位置

**日志显示**：
- 实时推送：逐行显示执行输出
- 彩色输出：stdout（青色）、stderr（红色）、状态（绿色）
- 自动滚动到最新内容
- 任务完成后日志保留在窗口中

**操作**：清空 | 复制

### ⚡ 快速执行命令

1. 点击顶部"⚡ 执行命令"
2. 输入命令并执行
3. 实时日志窗口自动弹出

**特点**：临时执行，不保存记录，始终显示日志

### 🔄 运行中任务管理

点击"🔄 运行中"查看正在执行的任务：
- 实时显示运行时长（每2秒刷新）
- **📺 查看日志** - 打开实时日志窗口
- **🛑 强制终止** - 强制 kill 任务（SIGKILL，谨慎使用）

### ⚙️ 设置

**实时日志显示**：
- 开启：执行任务时自动弹出日志窗口
- 关闭：仅显示通知（临时命令始终显示日志）

**任务超时时间**：
- 默认 3600秒（1小时）
- 常用值：300秒（5分钟）、1800秒（30分钟）、7200秒（2小时）

### 其他功能

- **视图模式**：列表视图 / 按钮视图
- **日志查询**：查看历史、按任务筛选、查看详情

## 💡 使用示例

**每天备份数据库**（每天定时 02:00）：
```bash
/usr/bin/mysqldump -u root -ppassword mydb > /backup/mydb_$(date +\%Y\%m\%d).sql
```

**每小时清理临时文件**（Cron：`0 * * * *`）：
```bash
find /tmp -type f -mtime +7 -delete
```

**每5分钟健康检查**（循环执行：300秒）：
```bash
/path/to/health_check.sh
```

**测试实时日志**（演示脚本）：
```bash
# Docker: /app/demo_realtime_log.sh
# 直接运行: /root/dotask/demo_realtime_log.sh
```

## 🗂️ 文件结构

```
├── app.py                  # 主应用
├── requirements.txt        # 依赖
├── Dockerfile              # Docker配置
├── docker-compose.yml      # Docker Compose配置
├── tasks.db                # SQLite数据库（自动创建）
├── demo_realtime_log.sh    # 演示脚本
├── templates/
│   ├── index.html          # 主界面
│   └── log_detail.html     # 日志详情
└── README.md
```

## 🔧 配置

### 时区配置

环境变量 `TIMEZONE`（默认 `Asia/Shanghai`）：

```bash
# 直接运行
TIMEZONE=America/New_York python app.py

# Docker
docker run -d -e TIMEZONE=America/New_York -p 5000:5000 task-scheduler

# Docker Compose（修改 docker-compose.yml）
environment:
  - TIMEZONE=America/New_York
```

常用时区：`Asia/Shanghai`、`Asia/Tokyo`、`America/New_York`、`Europe/London`、`UTC`

### 应用配置

在 `app.py` 中修改：
- `TASKS_DB_PATH` - 数据库路径
- `host / port` - 监听地址和端口
- 超时时间可在 Web 设置中配置

## 💾 数据库

SQLite 数据库（`tasks.db`）包含三个表：

**tasks 表**：任务配置（id、name、command、schedule_type、schedule_config、enabled）

**task_logs 表**：执行日志（id、task_id、task_name、command、output、error、exit_code、started_at、finished_at）

**settings 表**：系统设置（key、value、updated_at）

## 🔌 API 接口

**任务**：
- `GET/POST /api/tasks` - 获取/创建任务
- `PUT/DELETE /api/tasks/<id>` - 更新/删除任务
- `POST /api/tasks/<id>/run` - 立即执行
- `GET /api/tasks/<execution_id>/stream` - SSE 实时日志流

**命令**：
- `POST /api/commands/run` - 执行临时命令

**运行中任务**：
- `GET /api/running_tasks` - 获取运行中任务
- `POST /api/running_tasks/<execution_id>/kill` - 强制终止

**日志**：
- `GET /api/logs` - 获取日志
- `DELETE /api/logs/<id>` - 删除日志
- `POST /api/logs/clear` - 清空日志

**设置**：
- `GET/POST /api/settings/view_mode` - 视图模式
- `GET/POST /api/settings/show_realtime_log` - 实时日志显示
- `GET/POST /api/settings/task_timeout` - 任务超时时间

## 🛡️ 安全建议

1. 生产环境使用反向代理（Nginx）+ HTTPS
2. 添加身份认证机制
3. 谨慎配置任务命令，避免执行不可信代码
4. Docker 中设置资源限制
5. 定期清理历史日志

## 📝 依赖

```
Flask==3.0.0        # Web 框架
APScheduler==3.10.4 # 任务调度
pytz==2024.1        # 时区
```

## 🐛 故障排查

**任务未执行**：检查任务是否启用、调度配置是否正确

**任务失败**：查看日志错误信息、确认命令路径和权限

**时区错误**：检查环境变量 `TIMEZONE`，重启服务

## 📄 许可证

MIT License

---

如有问题或建议，欢迎提交 Issue！

