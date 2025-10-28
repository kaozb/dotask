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
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import logging
import pytz
import threading
import queue
import time

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

# 全局字典，用于存储运行中任务的日志队列
running_tasks = {}
running_tasks_lock = threading.Lock()

# 存储运行中任务的进程对象
running_processes = {}
running_processes_lock = threading.Lock()


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
    
    # 设置默认实时日志显示开关
    cursor_tasks.execute('''
        INSERT OR IGNORE INTO settings (key, value)
        VALUES ('show_realtime_log', '1')
    ''')
    
    # 设置默认超时时间（秒）
    cursor_tasks.execute('''
        INSERT OR IGNORE INTO settings (key, value)
        VALUES ('task_timeout', '3600')
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


def get_task_timeout():
    """获取全局任务超时时间（秒）"""
    try:
        conn = sqlite3.connect(TASKS_DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM settings WHERE key = ?', ('task_timeout',))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return int(result[0])
        return 3600  # 默认1小时
    except:
        return 3600  # 出错时使用默认值


def execute_command_temp(command, execution_id):
    """临时执行命令（不保存到数据库）"""
    started_at = datetime.now()
    
    # 创建日志队列用于实时推送
    log_queue = queue.Queue()
    with running_tasks_lock:
        running_tasks[execution_id] = {
            'queue': log_queue,
            'task_id': 0,
            'task_name': '临时命令',
            'started_at': started_at,
            'finished': False
        }
    
    output_lines = []
    error_lines = []
    exit_code = 0
    
    try:
        # 使用Popen实时读取输出
        process = subprocess.Popen(
            command,
            shell=True,
            executable='/bin/bash',
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # 行缓冲
        )
        
        # 存储进程对象
        with running_processes_lock:
            running_processes[execution_id] = process
        
        # 发送开始消息
        log_queue.put({
            'type': 'start',
            'task_name': '临时命令',
            'command': command,
            'started_at': started_at.strftime('%Y-%m-%d %H:%M:%S')
        })
        
        # 创建线程读取stdout和stderr
        def read_output(pipe, is_stderr=False):
            for line in iter(pipe.readline, ''):
                if not line:
                    break
                line = line.rstrip('\n')
                if is_stderr:
                    error_lines.append(line)
                else:
                    output_lines.append(line)
                
                # 推送实时日志
                log_queue.put({
                    'type': 'log',
                    'data': line,
                    'is_stderr': is_stderr
                })
            pipe.close()
        
        stdout_thread = threading.Thread(target=read_output, args=(process.stdout, False))
        stderr_thread = threading.Thread(target=read_output, args=(process.stderr, True))
        
        stdout_thread.start()
        stderr_thread.start()
        
        # 等待进程完成（使用配置的超时时间）
        timeout_seconds = get_task_timeout()
        try:
            exit_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            timeout_hours = timeout_seconds / 3600
            if timeout_hours >= 1:
                timeout_msg = f'命令执行超时（{timeout_hours:.1f}小时）' if timeout_hours != int(timeout_hours) else f'命令执行超时（{int(timeout_hours)}小时）'
            else:
                timeout_msg = f'命令执行超时（{timeout_seconds}秒）'
            error_lines.append(timeout_msg)
            exit_code = -1
        
        # 等待读取线程完成
        stdout_thread.join()
        stderr_thread.join()
        
    except Exception as e:
        error_lines.append(f'执行异常: {str(e)}')
        exit_code = -1
    
    finished_at = datetime.now()
    
    # 发送完成消息
    log_queue.put({
        'type': 'finish',
        'exit_code': exit_code,
        'finished_at': finished_at.strftime('%Y-%m-%d %H:%M:%S'),
        'log_id': None  # 临时命令不保存到数据库
    })
    
    # 标记任务完成
    with running_tasks_lock:
        if execution_id in running_tasks:
            running_tasks[execution_id]['finished'] = True
    
    # 清理进程对象
    with running_processes_lock:
        if execution_id in running_processes:
            del running_processes[execution_id]
    
    logger.info(f"临时命令执行完成，退出码: {exit_code}")


def execute_task(task_id, task_name, command, execution_id=None):
    """执行任务"""
    started_at = datetime.now()
    
    # 如果有execution_id，说明是手动执行，需要实时推送日志
    log_queue = None
    if execution_id:
        log_queue = queue.Queue()
        with running_tasks_lock:
            running_tasks[execution_id] = {
                'queue': log_queue,
                'task_id': task_id,
                'task_name': task_name,
                'started_at': started_at,
                'finished': False
            }
    
    output_lines = []
    error_lines = []
    exit_code = 0
    
    try:
        # 使用Popen实时读取输出
        process = subprocess.Popen(
            command,
            shell=True,
            executable='/bin/bash',
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # 行缓冲
        )
        
        # 存储进程对象（如果有execution_id）
        if execution_id:
            with running_processes_lock:
                running_processes[execution_id] = process
        
        # 发送开始消息
        if log_queue:
            log_queue.put({
                'type': 'start',
                'task_name': task_name,
                'command': command,
                'started_at': started_at.strftime('%Y-%m-%d %H:%M:%S')
            })
        
        # 创建线程读取stdout和stderr
        def read_output(pipe, is_stderr=False):
            for line in iter(pipe.readline, ''):
                if not line:
                    break
                line = line.rstrip('\n')
                if is_stderr:
                    error_lines.append(line)
                else:
                    output_lines.append(line)
                
                # 推送实时日志
                if log_queue:
                    log_queue.put({
                        'type': 'log',
                        'data': line,
                        'is_stderr': is_stderr
                    })
            pipe.close()
        
        stdout_thread = threading.Thread(target=read_output, args=(process.stdout, False))
        stderr_thread = threading.Thread(target=read_output, args=(process.stderr, True))
        
        stdout_thread.start()
        stderr_thread.start()
        
        # 等待进程完成（使用配置的超时时间）
        timeout_seconds = get_task_timeout()
        try:
            exit_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            timeout_hours = timeout_seconds / 3600
            if timeout_hours >= 1:
                timeout_msg = f'任务执行超时（{timeout_hours:.1f}小时）' if timeout_hours != int(timeout_hours) else f'任务执行超时（{int(timeout_hours)}小时）'
            else:
                timeout_msg = f'任务执行超时（{timeout_seconds}秒）'
            error_lines.append(timeout_msg)
            exit_code = -1
        
        # 等待读取线程完成
        stdout_thread.join()
        stderr_thread.join()
        
    except Exception as e:
        error_lines.append(f'执行异常: {str(e)}')
        exit_code = -1
    
    finished_at = datetime.now()
    
    output = '\n'.join(output_lines)
    error = '\n'.join(error_lines)
    
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
    log_id = cursor.lastrowid
    conn.close()
    
    # 发送完成消息
    if log_queue:
        log_queue.put({
            'type': 'finish',
            'exit_code': exit_code,
            'finished_at': finished_at.strftime('%Y-%m-%d %H:%M:%S'),
            'log_id': log_id
        })
        
        # 标记任务完成
        with running_tasks_lock:
            if execution_id in running_tasks:
                running_tasks[execution_id]['finished'] = True
        
        # 清理进程对象
        with running_processes_lock:
            if execution_id in running_processes:
                del running_processes[execution_id]
    
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
            # Cron表达式（指定时区）
            trigger = CronTrigger.from_crontab(config['expression'], timezone=timezone)
            scheduler.add_job(
                execute_task,
                trigger=trigger,
                id=job_id,
                args=[task_id, name, command],
                replace_existing=True
            )
        elif schedule_type == 'interval':
            # 间隔循环
            trigger = IntervalTrigger(seconds=config['seconds'], timezone=timezone)
            scheduler.add_job(
                execute_task,
                trigger=trigger,
                id=job_id,
                args=[task_id, name, command],
                replace_existing=True
            )
        elif schedule_type == 'daily':
            # 每天定时（指定时区）
            hour = config['hour']
            minute = config['minute']
            trigger = CronTrigger(hour=hour, minute=minute, timezone=timezone)
            scheduler.add_job(
                execute_task,
                trigger=trigger,
                id=job_id,
                args=[task_id, name, command],
                replace_existing=True
            )
        
        logger.info(f"任务 '{name}' 已添加到调度器")
    except Exception as e:
        logger.error(f"添加任务 '{name}' 失败: {str(e)}")


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
                if job:
                    if job.next_run_time:
                        next_run_time = job.next_run_time.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        logger.warning(f"任务 {task_id} ({task[1]}) 的 next_run_time 为 None")
                else:
                    logger.warning(f"任务 {task_id} ({task[1]}) 未在调度器中找到")
            except Exception as e:
                logger.error(f"获取任务 {task_id} ({task[1]}) 的下次运行时间失败: {str(e)}")
        
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
    
    # 生成唯一的执行ID
    execution_id = f'exec_{task_id}_{int(datetime.now().timestamp() * 1000)}'
    
    # 在新线程中异步执行任务
    thread = threading.Thread(
        target=execute_task,
        args=(task_id, name, command, execution_id)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'message': '任务已提交执行',
        'execution_id': execution_id
    })


@app.route('/api/tasks/<execution_id>/stream', methods=['GET'])
def stream_task_logs(execution_id):
    """SSE流式推送任务执行日志"""
    def generate():
        # 等待任务启动（最多5秒）
        wait_time = 0
        while wait_time < 5:
            with running_tasks_lock:
                if execution_id in running_tasks:
                    break
            time.sleep(0.1)
            wait_time += 0.1
        
        with running_tasks_lock:
            if execution_id not in running_tasks:
                yield f"data: {json.dumps({'type': 'error', 'message': '任务不存在或已结束'})}\n\n"
                return
            
            log_queue = running_tasks[execution_id]['queue']
        
        # 持续推送日志
        timeout_counter = 0
        while True:
            try:
                # 使用超时来定期检查任务是否完成
                msg = log_queue.get(timeout=1)
                timeout_counter = 0
                
                # 发送日志消息
                yield f"data: {json.dumps(msg)}\n\n"
                
                # 如果是结束消息，退出循环
                if msg.get('type') == 'finish':
                    break
                    
            except queue.Empty:
                # 队列为空，发送心跳
                timeout_counter += 1
                
                # 检查任务是否已完成
                with running_tasks_lock:
                    if execution_id in running_tasks and running_tasks[execution_id]['finished']:
                        break
                
                # 如果超过60秒没有新消息且任务未在运行列表中，断开连接
                if timeout_counter > 60:
                    with running_tasks_lock:
                        if execution_id not in running_tasks:
                            break
                
                # 发送心跳保持连接
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        
        # 清理
        with running_tasks_lock:
            if execution_id in running_tasks:
                del running_tasks[execution_id]
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


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


@app.route('/api/settings/show_realtime_log', methods=['GET'])
def get_show_realtime_log():
    """获取实时日志显示设置"""
    conn = sqlite3.connect(TASKS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', ('show_realtime_log',))
    result = cursor.fetchone()
    conn.close()
    
    show_realtime_log = result[0] if result else '1'
    return jsonify({'show_realtime_log': show_realtime_log == '1'})


@app.route('/api/settings/show_realtime_log', methods=['POST'])
def set_show_realtime_log():
    """设置实时日志显示"""
    data = request.json
    show_realtime_log = data.get('show_realtime_log', True)
    
    conn = sqlite3.connect(TASKS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO settings (key, value, updated_at)
        VALUES ('show_realtime_log', ?, CURRENT_TIMESTAMP)
    ''', ('1' if show_realtime_log else '0',))
    conn.commit()
    conn.close()
    
    return jsonify({'message': '实时日志显示设置已保存', 'show_realtime_log': show_realtime_log})


@app.route('/api/settings/task_timeout', methods=['GET'])
def get_task_timeout_setting():
    """获取任务超时时间设置"""
    conn = sqlite3.connect(TASKS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', ('task_timeout',))
    result = cursor.fetchone()
    conn.close()
    
    task_timeout = int(result[0]) if result else 3600
    return jsonify({'task_timeout': task_timeout})


@app.route('/api/settings/task_timeout', methods=['POST'])
def set_task_timeout_setting():
    """设置任务超时时间"""
    data = request.json
    task_timeout = data.get('task_timeout', 3600)
    
    # 验证超时时间（至少60秒，最多24小时）
    try:
        task_timeout = int(task_timeout)
        if task_timeout < 60:
            return jsonify({'error': '超时时间不能小于60秒'}), 400
        if task_timeout > 86400:
            return jsonify({'error': '超时时间不能大于24小时（86400秒）'}), 400
    except ValueError:
        return jsonify({'error': '无效的超时时间'}), 400
    
    conn = sqlite3.connect(TASKS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO settings (key, value, updated_at)
        VALUES ('task_timeout', ?, CURRENT_TIMESTAMP)
    ''', (str(task_timeout),))
    conn.commit()
    conn.close()
    
    return jsonify({'message': '超时时间已保存', 'task_timeout': task_timeout})


@app.route('/api/running_tasks', methods=['GET'])
def get_running_tasks():
    """获取当前运行中的任务列表"""
    running_list = []
    
    with running_tasks_lock:
        for execution_id, task_info in running_tasks.items():
            if not task_info.get('finished', False):
                # 计算运行时长
                started_at = task_info['started_at']
                elapsed = (datetime.now() - started_at).total_seconds()
                
                running_list.append({
                    'execution_id': execution_id,
                    'task_id': task_info['task_id'],
                    'task_name': task_info['task_name'],
                    'started_at': started_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'elapsed_seconds': int(elapsed)
                })
    
    return jsonify(running_list)


@app.route('/api/running_tasks/<execution_id>/kill', methods=['POST'])
def kill_running_task(execution_id):
    """强制终止运行中的任务"""
    with running_processes_lock:
        if execution_id not in running_processes:
            return jsonify({'error': '任务不存在或已结束'}), 404
        
        process = running_processes[execution_id]
        
        try:
            # 强制终止进程
            process.kill()
            logger.info(f"强制终止任务: {execution_id}")
            return jsonify({'message': '任务已终止', 'execution_id': execution_id})
        except Exception as e:
            logger.error(f"终止任务失败: {str(e)}")
            return jsonify({'error': f'终止失败: {str(e)}'}), 500


@app.route('/api/commands/run', methods=['POST'])
def run_command():
    """直接执行命令（临时执行，不创建任务）"""
    data = request.json
    command = data.get('command', '').strip()
    
    if not command:
        return jsonify({'error': '命令不能为空'}), 400
    
    # 生成唯一的执行ID
    execution_id = f'cmd_{int(datetime.now().timestamp() * 1000)}'
    
    # 在新线程中异步执行命令（不记录到数据库）
    thread = threading.Thread(
        target=execute_command_temp,
        args=(command, execution_id)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'message': '命令已提交执行',
        'execution_id': execution_id
    })


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

