#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
轻量级定时任务服务
使用Flask + APScheduler实现，资源占用极低
"""

import os
import sqlite3
import subprocess
import json
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import logging
import pytz

# 配置
TASKS_DB_PATH = 'tasks.db'
LOGS_DB_PATH = 'tasks.db'

TIMEZONE = os.environ.get('TIMEZONE', 'Asia/Shanghai')  # 默认时区：上海（东八区）



# 创建Flask应用
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建调度器（使用配置的时区）
try:
    timezone = pytz.timezone(TIMEZONE)
    logger.info(f"使用时区: {TIMEZONE}")
except Exception as e:
    logger.warning(f"时区 '{TIMEZONE}' 无效，使用默认时区 'Asia/Shanghai': {e}")
    timezone = pytz.timezone('Asia/Shanghai')

scheduler = BackgroundScheduler(timezone=timezone)
scheduler.start()


def init_db():
    """初始化数据库"""
    # 初始化任务数据库
    conn_tasks = sqlite3.connect(TASKS_DB_PATH)
    cursor_tasks = conn_tasks.cursor()
    
    # 创建任务表
    cursor_tasks.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            command TEXT NOT NULL,
            schedule_type TEXT NOT NULL,
            schedule_config TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 创建配置表（用于存储界面设置等）
    cursor_tasks.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 设置默认视图模式
    cursor_tasks.execute('''
        INSERT OR IGNORE INTO settings (key, value)
        VALUES ('view_mode', 'list')
    ''')
    
    conn_tasks.commit()
    conn_tasks.close()
    
    # 初始化日志数据库
    conn_logs = sqlite3.connect(LOGS_DB_PATH)
    cursor_logs = conn_logs.cursor()
    
    # 创建日志表
    cursor_logs.execute('''
        CREATE TABLE IF NOT EXISTS task_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            task_name TEXT NOT NULL,
            command TEXT NOT NULL,
            output TEXT,
            error TEXT,
            exit_code INTEGER,
            started_at TIMESTAMP,
            finished_at TIMESTAMP
        )
    ''')
    
    conn_logs.commit()
    conn_logs.close()


def execute_task(task_id, task_name, command):
    """执行任务"""
    started_at = datetime.now()
    
    try:
        # 在bash环境中执行命令
        result = subprocess.run(
            command,
            shell=True,
            executable='/bin/bash',
            capture_output=True,
            text=True,
            timeout=3600  # 1小时超时
        )
        
        output = result.stdout
        error = result.stderr
        exit_code = result.returncode
        
    except subprocess.TimeoutExpired:
        output = ''
        error = '任务执行超时（1小时）'
        exit_code = -1
    except Exception as e:
        output = ''
        error = f'执行异常: {str(e)}'
        exit_code = -1
    
    finished_at = datetime.now()
    
    # 记录日志到数据库
    conn = sqlite3.connect(LOGS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO task_logs 
        (task_id, task_name, command, output, error, exit_code, started_at, finished_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (task_id, task_name, command, output, error, exit_code, 
          started_at.strftime('%Y-%m-%d %H:%M:%S'), finished_at.strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()
    
    logger.info(f"任务 '{task_name}' 执行完成，退出码: {exit_code}")


def add_job_to_scheduler(task):
    """将任务添加到调度器"""
    task_id, name, command, schedule_type, schedule_config, enabled = task
    
    if not enabled:
        return
    
    job_id = f'task_{task_id}'
    config = json.loads(schedule_config)
    
    try:
        if schedule_type == 'cron':
            # Cron表达式
            trigger = CronTrigger.from_crontab(config['expression'])
            scheduler.add_job(
                execute_task,
                trigger=trigger,
                id=job_id,
                args=[task_id, name, command],
                replace_existing=True
            )
        elif schedule_type == 'interval':
            # 间隔循环
            trigger = IntervalTrigger(seconds=config['seconds'])
            scheduler.add_job(
                execute_task,
                trigger=trigger,
                id=job_id,
                args=[task_id, name, command],
                replace_existing=True
            )
        elif schedule_type == 'daily':
            # 每天定时
            hour = config['hour']
            minute = config['minute']
            trigger = CronTrigger(hour=hour, minute=minute)
            scheduler.add_job(
                execute_task,
                trigger=trigger,
                id=job_id,
                args=[task_id, name, command],
                replace_existing=True
            )
        
        logger.info(f"任务 '{name}' 已添加到调度器")
    except Exception as e:
        logger.error(f"添加任务失败: {str(e)}")


def load_tasks():
    """从数据库加载所有任务到调度器"""
    conn = sqlite3.connect(TASKS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, command, schedule_type, schedule_config, enabled FROM tasks')
    tasks = cursor.fetchall()
    conn.close()
    
    # 清除现有的所有任务
    scheduler.remove_all_jobs()
    
    # 重新加载所有任务
    for task in tasks:
        add_job_to_scheduler(task)


@app.route('/')
def index():
    """主页"""
    # 获取保存的视图模式
    conn = sqlite3.connect(TASKS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', ('view_mode',))
    result = cursor.fetchone()
    conn.close()
    
    view_mode = result[0] if result else 'list'
    return render_template('index.html', view_mode=view_mode)


@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    """获取所有任务"""
    conn = sqlite3.connect(TASKS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, name, command, schedule_type, schedule_config, enabled, 
               created_at, updated_at
        FROM tasks
        ORDER BY id DESC
    ''')
    tasks = cursor.fetchall()
    conn.close()
    
    result = []
    for task in tasks:
        task_id = task[0]
        
        # 获取下次执行时间
        next_run_time = None
        if task[5]:  # 如果任务已启用
            try:
                job = scheduler.get_job(f'task_{task_id}')
                if job and job.next_run_time:
                    next_run_time = job.next_run_time.strftime('%Y-%m-%d %H:%M:%S')
            except:
                pass
        
        result.append({
            'id': task_id,
            'name': task[1],
            'command': task[2],
            'schedule_type': task[3],
            'schedule_config': json.loads(task[4]),
            'enabled': bool(task[5]),
            'created_at': task[6],
            'updated_at': task[7],
            'next_run_time': next_run_time
        })
    
    return jsonify(result)


@app.route('/api/tasks', methods=['POST'])
def create_task():
    """创建任务"""
    data = request.json
    
    name = data.get('name')
    command = data.get('command')
    schedule_type = data.get('schedule_type')
    schedule_config = data.get('schedule_config')
    
    if not all([name, command, schedule_type, schedule_config]):
        return jsonify({'error': '参数不完整'}), 400
    
    conn = sqlite3.connect(TASKS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO tasks (name, command, schedule_type, schedule_config)
        VALUES (?, ?, ?, ?)
    ''', (name, command, schedule_type, json.dumps(schedule_config)))
    conn.commit()
    task_id = cursor.lastrowid
    conn.close()
    
    # 重新加载任务
    load_tasks()
    
    return jsonify({'id': task_id, 'message': '任务创建成功'})


@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def update_task(task_id):
    """更新任务"""
    data = request.json
    
    conn = sqlite3.connect(TASKS_DB_PATH)
    cursor = conn.cursor()
    
    # 构建更新语句
    updates = []
    params = []
    
    if 'name' in data:
        updates.append('name = ?')
        params.append(data['name'])
    if 'command' in data:
        updates.append('command = ?')
        params.append(data['command'])
    if 'schedule_type' in data:
        updates.append('schedule_type = ?')
        params.append(data['schedule_type'])
    if 'schedule_config' in data:
        updates.append('schedule_config = ?')
        params.append(json.dumps(data['schedule_config']))
    if 'enabled' in data:
        updates.append('enabled = ?')
        params.append(1 if data['enabled'] else 0)
    
    updates.append('updated_at = CURRENT_TIMESTAMP')
    params.append(task_id)
    
    cursor.execute(f'''
        UPDATE tasks 
        SET {', '.join(updates)}
        WHERE id = ?
    ''', params)
    conn.commit()
    conn.close()
    
    # 重新加载任务
    load_tasks()
    
    return jsonify({'message': '任务更新成功'})


@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    """删除任务"""
    conn = sqlite3.connect(TASKS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()
    
    # 从调度器移除
    try:
        scheduler.remove_job(f'task_{task_id}')
    except:
        pass
    
    return jsonify({'message': '任务删除成功'})


@app.route('/api/tasks/<int:task_id>/run', methods=['POST'])
def run_task(task_id):
    """立即执行任务"""
    conn = sqlite3.connect(TASKS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT name, command FROM tasks WHERE id = ?', (task_id,))
    task = cursor.fetchone()
    conn.close()
    
    if not task:
        return jsonify({'error': '任务不存在'}), 404
    
    name, command = task
    
    # 异步执行任务
    scheduler.add_job(
        execute_task,
        args=[task_id, name, command],
        id=f'manual_{task_id}_{datetime.now().timestamp()}'
    )
    
    return jsonify({'message': '任务已提交执行'})


@app.route('/api/logs', methods=['GET'])
def get_logs():
    """获取日志"""
    task_id = request.args.get('task_id')
    limit = request.args.get('limit', 100, type=int)
    
    conn = sqlite3.connect(LOGS_DB_PATH)
    cursor = conn.cursor()
    
    if task_id:
        cursor.execute('''
            SELECT id, task_id, task_name, command, output, error, exit_code,
                   started_at, finished_at
            FROM task_logs
            WHERE task_id = ?
            ORDER BY id DESC
            LIMIT ?
        ''', (task_id, limit))
    else:
        cursor.execute('''
            SELECT id, task_id, task_name, command, output, error, exit_code,
                   started_at, finished_at
            FROM task_logs
            ORDER BY id DESC
            LIMIT ?
        ''', (limit,))
    
    logs = cursor.fetchall()
    conn.close()
    
    result = []
    for log in logs:
        result.append({
            'id': log[0],
            'task_id': log[1],
            'task_name': log[2],
            'command': log[3],
            'output': log[4],
            'error': log[5],
            'exit_code': log[6],
            'started_at': log[7],
            'finished_at': log[8]
        })
    
    return jsonify(result)


@app.route('/api/logs/<int:log_id>', methods=['DELETE'])
def delete_log(log_id):
    """删除日志"""
    conn = sqlite3.connect(LOGS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM task_logs WHERE id = ?', (log_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'message': '日志删除成功'})


@app.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    """清空日志"""
    task_id = request.args.get('task_id')
    
    conn = sqlite3.connect(LOGS_DB_PATH)
    cursor = conn.cursor()
    
    if task_id:
        cursor.execute('DELETE FROM task_logs WHERE task_id = ?', (task_id,))
    else:
        cursor.execute('DELETE FROM task_logs')
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': '日志已清空'})


@app.route('/api/settings/view_mode', methods=['GET'])
def get_view_mode():
    """获取视图模式"""
    conn = sqlite3.connect(TASKS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', ('view_mode',))
    result = cursor.fetchone()
    conn.close()
    
    view_mode = result[0] if result else 'list'
    return jsonify({'view_mode': view_mode})


@app.route('/api/settings/view_mode', methods=['POST'])
def set_view_mode():
    """设置视图模式"""
    data = request.json
    view_mode = data.get('view_mode', 'list')
    
    if view_mode not in ['list', 'button']:
        return jsonify({'error': '无效的视图模式'}), 400
    
    conn = sqlite3.connect(TASKS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO settings (key, value, updated_at)
        VALUES ('view_mode', ?, CURRENT_TIMESTAMP)
    ''', (view_mode,))
    conn.commit()
    conn.close()
    
    return jsonify({'message': '视图模式已保存', 'view_mode': view_mode})


@app.route('/log/<int:log_id>')
def log_detail(log_id):
    """查看日志详情"""
    conn = sqlite3.connect(LOGS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, task_id, task_name, command, output, error, exit_code,
               started_at, finished_at
        FROM task_logs
        WHERE id = ?
    ''', (log_id,))
    log = cursor.fetchone()
    conn.close()
    
    if not log:
        return '日志不存在', 404
    
    # 计算执行时长
    from datetime import datetime
    started_at = datetime.strptime(log[7], '%Y-%m-%d %H:%M:%S')
    finished_at = datetime.strptime(log[8], '%Y-%m-%d %H:%M:%S')
    duration = finished_at - started_at
    
    # 格式化时长
    total_seconds = int(duration.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    if hours > 0:
        duration_str = f"{hours}小时{minutes}分钟{seconds}秒"
    elif minutes > 0:
        duration_str = f"{minutes}分钟{seconds}秒"
    else:
        duration_str = f"{seconds}秒"
    
    log_data = {
        'id': log[0],
        'task_id': log[1],
        'task_name': log[2],
        'command': log[3],
        'output': log[4],
        'error': log[5],
        'exit_code': log[6],
        'started_at': log[7],
        'finished_at': log[8]
    }
    
    return render_template('log_detail.html', log=log_data, duration=duration_str)


if __name__ == '__main__':
    # 初始化数据库
    init_db()
    
    # 加载任务
    load_tasks()
    
    # 启动Flask应用
    logger.info("轻量级定时任务服务启动...")
    app.run(host='0.0.0.0', port=5000, debug=False)

