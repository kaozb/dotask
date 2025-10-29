#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
认证中间件
实现用户注册、登录、权限验证功能
"""

import hashlib
import os
import sqlite3
# 移除未使用的导入


def hash_password(password, salt=None):
    """密码哈希"""
    if salt is None:
        salt = os.urandom(32)
    elif isinstance(salt, str):
        salt = bytes.fromhex(salt)
    
    # 使用 PBKDF2 哈希算法
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return pwd_hash.hex(), salt.hex()


def verify_password(stored_password, stored_salt, provided_password):
    """验证密码"""
    pwd_hash, _ = hash_password(provided_password, stored_salt)
    return pwd_hash == stored_password


def init_auth_db(db_path):
    """初始化用户表"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 创建用户表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 添加认证相关的设置
    cursor.execute('''
        INSERT OR IGNORE INTO settings (key, value)
        VALUES ('allow_registration', '1')
    ''')
    
    cursor.execute('''
        INSERT OR IGNORE INTO settings (key, value)
        VALUES ('require_login', '0')
    ''')
    
    conn.commit()
    conn.close()


def get_auth_settings(db_path):
    """获取认证设置"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('SELECT value FROM settings WHERE key = ?', ('allow_registration',))
    allow_reg = cursor.fetchone()
    
    cursor.execute('SELECT value FROM settings WHERE key = ?', ('require_login',))
    require_login = cursor.fetchone()
    
    conn.close()
    
    return {
        'allow_registration': allow_reg[0] == '1' if allow_reg else True,
        'require_login': require_login[0] == '1' if require_login else False
    }


def register_user(db_path, username, password):
    """注册新用户"""
    # 检查是否允许注册
    settings = get_auth_settings(db_path)
    if not settings['allow_registration']:
        return False, '注册功能已关闭'
    
    # 验证用户名和密码
    if not username or len(username) < 3:
        return False, '用户名至少3个字符'
    
    if not password or len(password) < 6:
        return False, '密码至少6个字符'
    
    # 哈希密码
    pwd_hash, salt = hash_password(password)
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (username, password_hash, password_salt)
            VALUES (?, ?, ?)
        ''', (username, pwd_hash, salt))
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return True, user_id
    except sqlite3.IntegrityError:
        return False, '用户名已存在'
    except Exception as e:
        return False, f'注册失败: {str(e)}'


def authenticate_user(db_path, username, password):
    """验证用户登录"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, password_hash, password_salt FROM users WHERE username = ?
    ''', (username,))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        return False, '用户名或密码错误'
    
    user_id, stored_hash, stored_salt = user
    
    if verify_password(stored_hash, stored_salt, password):
        return True, user_id
    else:
        return False, '用户名或密码错误'


def get_user_info(db_path, user_id):
    """获取用户信息"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, username, created_at FROM users WHERE id = ?
    ''', (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return {
            'id': user[0],
            'username': user[1],
            'created_at': user[2]
        }
    return None


def get_all_users(db_path):
    """获取所有用户列表（管理用）"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, username, created_at FROM users ORDER BY id
    ''')
    users = cursor.fetchall()
    conn.close()
    
    return [{'id': u[0], 'username': u[1], 'created_at': u[2]} for u in users]


def delete_user(db_path, user_id):
    """删除用户"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0


def change_password(db_path, user_id, old_password, new_password):
    """修改密码"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT password_hash, password_salt FROM users WHERE id = ?
    ''', (user_id,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return False, '用户不存在'
    
    stored_hash, stored_salt = user
    
    # 验证旧密码
    if not verify_password(stored_hash, stored_salt, old_password):
        conn.close()
        return False, '原密码错误'
    
    # 验证新密码
    if not new_password or len(new_password) < 6:
        conn.close()
        return False, '新密码至少6个字符'
    
    # 设置新密码
    new_hash, new_salt = hash_password(new_password)
    cursor.execute('''
        UPDATE users SET password_hash = ?, password_salt = ? WHERE id = ?
    ''', (new_hash, new_salt, user_id))
    conn.commit()
    conn.close()
    
    return True, '密码修改成功'


# AuthMiddleware 类已删除 - 未被使用

