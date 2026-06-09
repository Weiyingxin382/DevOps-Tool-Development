# -*- coding: utf-8 -*-
"""
局域网轻量化运维监控工具
==========================
功能：
1. 局域网设备监测 - 批量 ping IP，在线绿色/离线红色
2. 服务状态巡检 - 检测端口开放状态
3. 日志记录 - 自动记录并保存到本地文件
4. 故障提示 - 异常自动标红警告

技术栈：Python + Flask，单文件，无需数据库和登录
"""

import os
import re
import json
import socket
import threading
import time
import subprocess
import platform
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template_string, request, jsonify, Response

# ============================================================
# 初始化 Flask 应用
# ============================================================
app = Flask(__name__)
app.config['SECRET_KEY'] = 'lan-monitor-secret-key-2024'

# ============================================================
# 全局数据存储（内存中，单文件无需数据库）
# ============================================================
devices = []   # 每项 {"id","name","ip","status","last_check"}
services = []  # 每项 {"id","name","ip","port","status","last_check"}
logs = []      # 每项 {"time","type","name","ip","port"(可选),"status","detail"}

# 文件路径
LOG_FILE = Path(__file__).parent / "lan_monitor_log.json"
DATA_FILE = Path(__file__).parent / "lan_monitor_data.json"

# 线程安全锁
data_lock = threading.Lock()

# 自动巡检配置
auto_scan_enabled = False
auto_scan_interval = 60  # 秒


# ============================================================
# 公共样式（所有页面共享的 CSS）
# ============================================================
COMMON_CSS = r"""
    * { margin:0; padding:0; box-sizing:border-box; }
    body {
        font-family:"Microsoft YaHei","PingFang SC","Helvetica Neue",Arial,sans-serif;
        background:#f0f2f5; color:#333; min-height:100vh;
    }
    .header {
        background:linear-gradient(135deg,#1a73e8,#0d5bbd); color:#fff;
        padding:0 24px; height:56px; display:flex; align-items:center;
        justify-content:space-between; box-shadow:0 2px 8px rgba(0,0,0,0.15);
        position:sticky; top:0; z-index:100;
    }
    .header h1 { font-size:20px; font-weight:600; }
    .header .nav a {
        color:rgba(255,255,255,0.85); text-decoration:none; margin-left:8px;
        padding:6px 12px; border-radius:4px; transition:background 0.2s; font-size:14px;
    }
    .header .nav a:hover, .header .nav a.active { background:rgba(255,255,255,0.15); color:#fff; }
    .container { max-width:1200px; margin:0 auto; padding:20px 24px; }
    .card {
        background:#fff; border-radius:8px; box-shadow:0 1px 4px rgba(0,0,0,0.08);
        padding:20px; margin-bottom:20px;
    }
    .card h2 {
        font-size:18px; margin-bottom:16px; color:#1a73e8;
        border-bottom:2px solid #e8f0fe; padding-bottom:8px;
    }
    .stats { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:20px; }
    .stat-card {
        background:#fff; border-radius:8px; padding:18px; text-align:center;
        box-shadow:0 1px 4px rgba(0,0,0,0.08);
    }
    .stat-card .number { font-size:32px; font-weight:700; }
    .stat-card .label { color:#666; font-size:13px; margin-top:4px; }
    .stat-card.online .number { color:#0f9d58; }
    .stat-card.offline .number { color:#ea4335; }
    .stat-card.open .number { color:#0f9d58; }
    .stat-card.closed .number { color:#ea4335; }
    table { width:100%; border-collapse:collapse; font-size:14px; }
    thead th {
        background:#f8f9fa; padding:10px 12px; text-align:left;
        border-bottom:2px solid #dee2e6; font-weight:600; white-space:nowrap;
    }
    tbody td { padding:10px 12px; border-bottom:1px solid #eee; vertical-align:middle; }
    tbody tr:hover { background:#f8f9fa; }
    .badge {
        display:inline-block; padding:3px 10px; border-radius:12px;
        font-size:12px; font-weight:600; color:#fff;
    }
    .badge-success { background:#0f9d58; }
    .badge-danger { background:#ea4335; }
    .badge-warning { background:#f9ab00; }
    .badge-info { background:#4285f4; }
    .btn {
        display:inline-block; padding:8px 18px; border:none; border-radius:4px;
        cursor:pointer; font-size:14px; font-weight:500; text-decoration:none;
        transition:all 0.2s; color:#fff;
    }
    .btn-primary { background:#1a73e8; }
    .btn-primary:hover { background:#1557b0; }
    .btn-success { background:#0f9d58; }
    .btn-success:hover { background:#0b8043; }
    .btn-danger { background:#ea4335; }
    .btn-danger:hover { background:#d33426; }
    .btn-sm { padding:4px 12px; font-size:12px; }
    .btn-group { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:16px; }
    .form-group { margin-bottom:12px; }
    .form-group label { display:inline-block; width:80px; font-weight:600; font-size:14px; }
    .form-group input {
        padding:6px 10px; border:1px solid #ddd; border-radius:4px;
        font-size:14px; width:200px; transition:border-color 0.2s;
    }
    .form-group input:focus {
        outline:none; border-color:#1a73e8; box-shadow:0 0 0 2px rgba(26,115,232,0.15);
    }
    .form-row { display:flex; flex-wrap:wrap; gap:16px; align-items:flex-end; }
    .alert {
        padding:10px 16px; border-radius:4px; margin-bottom:16px; font-size:14px;
    }
    .alert-info { background:#e8f0fe; color:#1967d2; border:1px solid #d2e3fc; }
    .alert-danger { background:#fce8e6; color:#c5221f; border:1px solid #f5c6c2; }
    .action-bar {
        display:flex; justify-content:space-between; align-items:center;
        margin-bottom:16px; flex-wrap:wrap; gap:10px;
    }
    .empty-state { text-align:center; padding:40px; color:#999; }
    .empty-state .icon { font-size:48px; margin-bottom:10px; }
    .filter-bar { margin-bottom:16px; display:flex; gap:12px; align-items:center; }
    .filter-bar select, .filter-bar input {
        padding:6px 10px; border:1px solid #ddd; border-radius:4px; font-size:14px;
    }
    .text-muted { color:#999; font-size:12px; }
    .text-danger { color:#ea4335; }
    .footer { text-align:center; padding:20px; color:#999; font-size:12px; }
    input[type="number"] { width:100px; }
"""

# ============================================================
# HTML 页面模板（每个页面独立完整，避免 Jinja2 继承问题）
# ============================================================

# --- 仪表盘 ---
DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>仪表盘 - 局域网运维监控工具</title>
<style>""" + COMMON_CSS + r"""</style>
</head>
<body>
<div class="header">
    <h1>🖥️ 局域网运维监控工具</h1>
    <div class="nav" id="navbar">
        <a href="/" data-page="dashboard">📊 仪表盘</a>
        <a href="/devices" data-page="devices">🔍 设备管理</a>
        <a href="/services" data-page="services">🔌 服务管理</a>
        <a href="/logs" data-page="logs">📋 日志查看</a>
        <a href="/settings" data-page="settings">⚙️ 设置</a>
    </div>
</div>
<div class="container">
<h2 style="margin-bottom:16px;">📊 仪表盘</h2>
<div class="stats">
    <div class="stat-card online">
        <div class="number" id="stat-online">-</div>
        <div class="label">设备在线</div>
    </div>
    <div class="stat-card offline">
        <div class="number" id="stat-offline">-</div>
        <div class="label">设备离线</div>
    </div>
    <div class="stat-card open">
        <div class="number" id="stat-open">-</div>
        <div class="label">服务端口开放</div>
    </div>
    <div class="stat-card closed">
        <div class="number" id="stat-closed">-</div>
        <div class="label">服务端口关闭</div>
    </div>
</div>
<div id="alert-area"></div>
<div class="card">
    <div class="action-bar">
        <h2 style="border:none;margin:0;padding:0;">📡 快速巡检</h2>
        <div>
            <button class="btn btn-primary" onclick="quickScan()" id="btn-scan">🔄 立即巡检</button>
            <button class="btn btn-success" onclick="toggleAutoScan()" id="btn-auto">▶ 启动自动巡检</button>
            <a class="btn btn-primary btn-sm" href="/api/export/csv" style="font-size:14px;padding:8px 18px;">📥 导出CSV报告</a>
        </div>
    </div>
    <span class="text-muted" id="scan-status">就绪</span>
</div>
<div class="card">
    <h2>🖥️ 设备状态概览</h2>
    <div id="device-table-area">
        <div class="empty-state"><div class="icon">📭</div><p>暂无设备，请到"设备管理"页面添加</p></div>
    </div>
</div>
<div class="card">
    <h2>🔌 服务端口状态</h2>
    <div id="service-table-area">
        <div class="empty-state"><div class="icon">📭</div><p>暂无服务，请到"服务管理"页面添加</p></div>
    </div>
</div>
</div>
<div class="footer">局域网运维监控工具 | Python + Flask | 轻量化单文件部署</div>
<script src="https://cdn.bootcdn.net/ajax/libs/jquery/3.6.0/jquery.min.js"></script>
<script>
// 标记当前页面
$('#navbar a[data-page="dashboard"]').addClass('active');
// 计算故障持续时间
function calcDuration(since) {
    if (!since) return '-';
    var diff = Math.floor((new Date() - new Date(since)) / 1000);
    if (diff < 0) return '-';
    if (diff < 60) return diff + '秒';
    var m = Math.floor(diff / 60);
    var s = diff % 60;
    if (m < 60) return m + '分' + s + '秒';
    var h = Math.floor(m / 60);
    m = m % 60;
    return h + '时' + m + '分' + s + '秒';
}
function refreshDashboard() {
    $.get('/api/status', function(data) {
        $('#stat-online').text(data.stats.online);
        $('#stat-offline').text(data.stats.offline);
        $('#stat-open').text(data.stats.open);
        $('#stat-closed').text(data.stats.closed);
        var alerts = '';
        $.each(data.alerts, function(i, a) {
            alerts += '<div class="alert alert-danger"><strong>⚠️ 故障告警：</strong>' + a + '</div>';
        });
        $('#alert-area').html(alerts);
        var devHtml = '';
        if (data.devices.length === 0) {
            devHtml = '<div class="empty-state"><div class="icon">📭</div><p>暂无设备</p></div>';
        } else {
            devHtml = '<table><thead><tr><th>设备名称</th><th>IP地址</th><th>状态</th><th>故障持续</th><th>延迟/详情</th><th>最近检测</th></tr></thead><tbody>';
            $.each(data.devices, function(i, d) {
                var cls = d.status === 'online' ? 'badge-success' : 'badge-danger';
                var txt = d.status === 'online' ? '在线' : '离线';
                var dur = d.status === 'offline' ? calcDuration(d.failure_since) : '-';
                var durCls = d.status === 'offline' ? ' style="color:#ea4335;font-weight:600;"' : '';
                devHtml += '<tr><td><strong>' + d.name + '</strong></td><td>' + d.ip + '</td>' +
                    '<td><span class="badge ' + cls + '">' + txt + '</span></td>' +
                    '<td' + durCls + '>' + dur + '</td>' +
                    '<td>' + (d.detail || '-') + '</td>' +
                    '<td class="text-muted">' + (d.last_check || '未检测') + '</td></tr>';
            });
            devHtml += '</tbody></table>';
        }
        $('#device-table-area').html(devHtml);
        var svcHtml = '';
        if (data.services.length === 0) {
            svcHtml = '<div class="empty-state"><div class="icon">📭</div><p>暂无服务</p></div>';
        } else {
            svcHtml = '<table><thead><tr><th>服务名称</th><th>IP地址</th><th>端口</th><th>状态</th><th>故障持续</th><th>详情</th><th>最近检测</th></tr></thead><tbody>';
            $.each(data.services, function(i, s) {
                var cls = s.status === 'open' ? 'badge-success' : 'badge-danger';
                var txt = s.status === 'open' ? '开放' : '关闭';
                var dur = s.status === 'closed' ? calcDuration(s.failure_since) : '-';
                var durCls = s.status === 'closed' ? ' style="color:#ea4335;font-weight:600;"' : '';
                svcHtml += '<tr><td><strong>' + s.name + '</strong></td><td>' + s.ip + '</td>' +
                    '<td>' + s.port + '</td>' +
                    '<td><span class="badge ' + cls + '">' + txt + '</span></td>' +
                    '<td' + durCls + '>' + dur + '</td>' +
                    '<td>' + (s.detail || '-') + '</td>' +
                    '<td class="text-muted">' + (s.last_check || '未检测') + '</td></tr>';
            });
            svcHtml += '</tbody></table>';
        }
        $('#service-table-area').html(svcHtml);
        if (data.auto_scan) {
            $('#btn-auto').text('⏸ 停止自动巡检').removeClass('btn-success').addClass('btn-danger');
        } else {
            $('#btn-auto').text('▶ 启动自动巡检').removeClass('btn-danger').addClass('btn-success');
        }
    });
}
refreshDashboard();
setInterval(refreshDashboard, 10000);
function quickScan() {
    $('#scan-status').text('⏳ 正在扫描中...');
    $('#btn-scan').prop('disabled', true);
    $.get('/api/scan', function() {
        refreshDashboard();
        $('#scan-status').text('✅ 扫描完成 - ' + new Date().toLocaleTimeString());
        $('#btn-scan').prop('disabled', false);
    }).fail(function() {
        $('#scan-status').text('❌ 扫描失败');
        $('#btn-scan').prop('disabled', false);
    });
}
function toggleAutoScan() {
    $('#btn-auto').prop('disabled', true);
    $.post('/api/auto-scan/toggle', function() {
        refreshDashboard();
        $('#btn-auto').prop('disabled', false);
    });
}
</script>
</body>
</html>"""


# --- 设备管理 ---
DEVICES_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>设备管理 - 局域网运维监控工具</title>
<style>""" + COMMON_CSS + r"""</style>
</head>
<body>
<div class="header">
    <h1>🖥️ 局域网运维监控工具</h1>
    <div class="nav" id="navbar">
        <a href="/" data-page="dashboard">📊 仪表盘</a>
        <a href="/devices" data-page="devices">🔍 设备管理</a>
        <a href="/services" data-page="services">🔌 服务管理</a>
        <a href="/logs" data-page="logs">📋 日志查看</a>
        <a href="/settings" data-page="settings">⚙️ 设置</a>
    </div>
</div>
<div class="container">
<h2 style="margin-bottom:16px;">🔍 设备管理</h2>
<div class="card">
    <h2>➕ 添加设备</h2>
    <div class="form-row">
        <div class="form-group">
            <label for="dev-name">设备名称</label>
            <input type="text" id="dev-name" placeholder="如：主服务器">
        </div>
        <div class="form-group">
            <label for="dev-ip">IP 地址</label>
            <input type="text" id="dev-ip" placeholder="如：192.168.1.1">
        </div>
        <button class="btn btn-primary" onclick="addDevice()">添加设备</button>
    </div>
</div>
<div class="card">
    <h2>📦 批量添加IP范围</h2>
    <div class="form-row">
        <div class="form-group">
            <label for="ip-start">起始 IP</label>
            <input type="text" id="ip-start" placeholder="如：192.168.1.1">
        </div>
        <div class="form-group">
            <label for="ip-end">结束 IP</label>
            <input type="text" id="ip-end" placeholder="如：192.168.1.254">
        </div>
        <button class="btn btn-primary" onclick="batchAdd()">批量添加</button>
        <span class="text-muted">（自动生成范围内所有IP）</span>
    </div>
</div>
<div class="card">
    <div class="action-bar">
        <h2 style="border:none;margin:0;padding:0;">📋 设备列表 (<span id="dev-count">0</span>)</h2>
        <div>
            <button class="btn btn-primary btn-sm" onclick="scanAllDevices()">🔍 扫描全部</button>
            <button class="btn btn-danger btn-sm" onclick="clearAllDevices()">🗑️ 清空全部</button>
        </div>
    </div>
    <div id="device-list-area">
        <div class="empty-state"><div class="icon">📭</div><p>暂无设备</p></div>
    </div>
</div>
</div>
<div class="footer">局域网运维监控工具 | Python + Flask | 轻量化单文件部署</div>
<script src="https://cdn.bootcdn.net/ajax/libs/jquery/3.6.0/jquery.min.js"></script>
<script>
$('#navbar a[data-page="devices"]').addClass('active');
function dur(since) {
    if (!since) return '-';
    var d = Math.floor((new Date() - new Date(since)) / 1000);
    if (d < 0) return '-';
    if (d < 60) return d + '秒';
    var m = Math.floor(d / 60);
    if (m < 60) return m + '分' + (d%60) + '秒';
    var h = Math.floor(m / 60);
    return h + '时' + (m%60) + '分' + (d%60) + '秒';
}
function loadList() {
    $.get('/api/devices', function(data) {
        $('#dev-count').text(data.length);
        var html = '';
        if (data.length === 0) {
            html = '<div class="empty-state"><div class="icon">📭</div><p>暂无设备</p></div>';
        } else {
            html = '<table><thead><tr><th>设备名称</th><th>IP地址</th><th>状态</th><th>故障持续</th><th>最近检测</th><th>操作</th></tr></thead><tbody>';
            $.each(data, function(i, d) {
                var cls = d.status === 'online' ? 'badge-success' : (d.status === 'offline' ? 'badge-danger' : 'badge-info');
                var txt = d.status === 'online' ? '在线' : (d.status === 'offline' ? '离线' : '未检测');
                var dval = d.status === 'offline' ? dur(d.failure_since) : '-';
                var dc = d.status === 'offline' ? ' style="color:#ea4335;font-weight:600;"' : '';
                html += '<tr><td><strong>' + d.name + '</strong></td><td>' + d.ip + '</td>' +
                    '<td><span class="badge ' + cls + '">' + txt + '</span></td>' +
                    '<td' + dc + '>' + dval + '</td>' +
                    '<td class="text-muted">' + (d.last_check || '-') + '</td>' +
                    '<td><button class="btn btn-primary btn-sm" onclick="scanOne(\'' + d.id + '\')">检测</button> ' +
                    '<button class="btn btn-danger btn-sm" onclick="deleteOne(\'' + d.id + '\')">删除</button></td></tr>';
            });
            html += '</tbody></table>';
        }
        $('#device-list-area').html(html);
    });
}
loadList();
function addDevice() {
    var n = $('#dev-name').val().trim(), ip = $('#dev-ip').val().trim();
    if (!n || !ip) { alert('请填写名称和IP'); return; }
    $.post('/api/devices', {name:n, ip:ip}, function(d) {
        if (d.success) { $('#dev-name').val(''); $('#dev-ip').val(''); loadList(); }
        else { alert(d.message); }
    });
}
function batchAdd() {
    var s = $('#ip-start').val().trim(), e = $('#ip-end').val().trim();
    if (!s || !e) { alert('请填写起止IP'); return; }
    $.post('/api/devices/batch', {start:s, end:e}, function(d) {
        if (d.success) { alert('成功添加 ' + d.count + ' 个设备'); $('#ip-start').val(''); $('#ip-end').val(''); loadList(); }
        else { alert(d.message); }
    });
}
function scanAllDevices() { $.get('/api/scan/devices', function() { loadList(); }); }
function scanOne(id) { $.get('/api/scan/device/' + id, function() { loadList(); }); }
function deleteOne(id) { if (!confirm('确定删除？')) return; $.post('/api/devices/delete', {id:id}, function() { loadList(); }); }
function clearAllDevices() { if (!confirm('确定清空所有设备？')) return; $.post('/api/devices/clear', function() { loadList(); }); }
</script>
</body>
</html>"""


# --- 服务管理 ---
SERVICES_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>服务管理 - 局域网运维监控工具</title>
<style>""" + COMMON_CSS + r"""</style>
</head>
<body>
<div class="header">
    <h1>🖥️ 局域网运维监控工具</h1>
    <div class="nav" id="navbar">
        <a href="/" data-page="dashboard">📊 仪表盘</a>
        <a href="/devices" data-page="devices">🔍 设备管理</a>
        <a href="/services" data-page="services">🔌 服务管理</a>
        <a href="/logs" data-page="logs">📋 日志查看</a>
        <a href="/settings" data-page="settings">⚙️ 设置</a>
    </div>
</div>
<div class="container">
<h2 style="margin-bottom:16px;">🔌 服务管理</h2>
<div class="card">
    <h2>➕ 添加服务端口检测</h2>
    <div class="form-row">
        <div class="form-group">
            <label for="svc-name">服务名称</label>
            <input type="text" id="svc-name" placeholder="如：Web服务">
        </div>
        <div class="form-group">
            <label for="svc-ip">IP 地址</label>
            <input type="text" id="svc-ip" placeholder="如：192.168.1.1">
        </div>
        <div class="form-group">
            <label for="svc-port">端口号</label>
            <input type="number" id="svc-port" placeholder="如：80">
        </div>
        <button class="btn btn-primary" onclick="addService()">添加服务</button>
    </div>
</div>
<div class="card">
    <h2>⚡ 快捷添加常用端口</h2>
    <div class="form-row">
        <div class="form-group">
            <label for="quick-ip">目标 IP</label>
            <input type="text" id="quick-ip" placeholder="如：192.168.1.1">
        </div>
        <button class="btn btn-primary btn-sm" onclick="quickAddPorts()">一键添加</button>
        <span class="text-muted">FTP/SSH/HTTP/HTTPS/RDP/MySQL/PostgreSQL/Redis/HTTP备用</span>
    </div>
</div>
<div class="card">
    <div class="action-bar">
        <h2 style="border:none;margin:0;padding:0;">📋 服务列表 (<span id="svc-count">0</span>)</h2>
        <div>
            <button class="btn btn-primary btn-sm" onclick="scanAllServices()">🔍 扫描全部</button>
            <button class="btn btn-danger btn-sm" onclick="clearAllServices()">🗑️ 清空全部</button>
        </div>
    </div>
    <div id="service-list-area">
        <div class="empty-state"><div class="icon">📭</div><p>暂无服务</p></div>
    </div>
</div>
</div>
<div class="footer">局域网运维监控工具 | Python + Flask | 轻量化单文件部署</div>
<script src="https://cdn.bootcdn.net/ajax/libs/jquery/3.6.0/jquery.min.js"></script>
<script>
$('#navbar a[data-page="services"]').addClass('active');
function dur(since) {
    if (!since) return '-';
    var d = Math.floor((new Date() - new Date(since)) / 1000);
    if (d < 0) return '-';
    if (d < 60) return d + '秒';
    var m = Math.floor(d / 60);
    if (m < 60) return m + '分' + (d%60) + '秒';
    var h = Math.floor(m / 60);
    return h + '时' + (m%60) + '分' + (d%60) + '秒';
}
function loadList() {
    $.get('/api/services', function(data) {
        $('#svc-count').text(data.length);
        var html = '';
        if (data.length === 0) {
            html = '<div class="empty-state"><div class="icon">📭</div><p>暂无服务</p></div>';
        } else {
            html = '<table><thead><tr><th>服务名称</th><th>IP地址</th><th>端口</th><th>状态</th><th>故障持续</th><th>最近检测</th><th>操作</th></tr></thead><tbody>';
            $.each(data, function(i, s) {
                var cls = s.status === 'open' ? 'badge-success' : (s.status === 'closed' ? 'badge-danger' : 'badge-info');
                var txt = s.status === 'open' ? '开放' : (s.status === 'closed' ? '关闭' : '未检测');
                var dval = s.status === 'closed' ? dur(s.failure_since) : '-';
                var dc = s.status === 'closed' ? ' style="color:#ea4335;font-weight:600;"' : '';
                html += '<tr><td><strong>' + s.name + '</strong></td><td>' + s.ip + '</td>' +
                    '<td>' + s.port + '</td>' +
                    '<td><span class="badge ' + cls + '">' + txt + '</span></td>' +
                    '<td' + dc + '>' + dval + '</td>' +
                    '<td class="text-muted">' + (s.last_check || '-') + '</td>' +
                    '<td><button class="btn btn-primary btn-sm" onclick="scanOne(\'' + s.id + '\')">检测</button> ' +
                    '<button class="btn btn-danger btn-sm" onclick="deleteOne(\'' + s.id + '\')">删除</button></td></tr>';
            });
            html += '</tbody></table>';
        }
        $('#service-list-area').html(html);
    });
}
loadList();
function addService() {
    var n = $('#svc-name').val().trim(), ip = $('#svc-ip').val().trim(), p = $('#svc-port').val().trim();
    if (!n || !ip || !p) { alert('请填写完整信息'); return; }
    $.post('/api/services', {name:n, ip:ip, port:p}, function(d) {
        if (d.success) { $('#svc-name').val(''); $('#svc-ip').val(''); $('#svc-port').val(''); loadList(); }
        else { alert(d.message); }
    });
}
function quickAddPorts() {
    var ip = $('#quick-ip').val().trim();
    if (!ip) { alert('请输入目标IP'); return; }
    $.post('/api/services/quick', {ip:ip}, function(d) {
        if (d.success) { alert('成功添加 ' + d.count + ' 个常用端口检测'); loadList(); }
        else { alert(d.message); }
    });
}
function scanAllServices() { $.get('/api/scan/services', function() { loadList(); }); }
function scanOne(id) { $.get('/api/scan/service/' + id, function() { loadList(); }); }
function deleteOne(id) { if (!confirm('确定删除？')) return; $.post('/api/services/delete', {id:id}, function() { loadList(); }); }
function clearAllServices() { if (!confirm('确定清空所有服务？')) return; $.post('/api/services/clear', function() { loadList(); }); }
</script>
</body>
</html>"""


# --- 日志查看 ---
LOGS_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>日志查看 - 局域网运维监控工具</title>
<style>""" + COMMON_CSS + r"""</style>
</head>
<body>
<div class="header">
    <h1>🖥️ 局域网运维监控工具</h1>
    <div class="nav" id="navbar">
        <a href="/" data-page="dashboard">📊 仪表盘</a>
        <a href="/devices" data-page="devices">🔍 设备管理</a>
        <a href="/services" data-page="services">🔌 服务管理</a>
        <a href="/logs" data-page="logs">📋 日志查看</a>
        <a href="/settings" data-page="settings">⚙️ 设置</a>
    </div>
</div>
<div class="container">
<h2 style="margin-bottom:16px;">📋 日志查看</h2>
<div class="card">
    <div class="action-bar">
        <h2 style="border:none;margin:0;padding:0;">📝 巡检日志 (共 <span id="log-count">0</span> 条)</h2>
        <div>
            <button class="btn btn-primary btn-sm" onclick="refreshLogs()">🔄 刷新</button>
            <button class="btn btn-danger btn-sm" onclick="clearLogs()">🗑️ 清空日志</button>
            <a class="btn btn-success btn-sm" href="/api/logs/export" target="_blank">📥 导出日志</a>
        </div>
    </div>
    <div class="filter-bar">
        <label>类型：</label>
        <select id="filter-type" onchange="refreshLogs()">
            <option value="all">全部</option>
            <option value="device">设备</option>
            <option value="service">服务</option>
        </select>
        <label>状态：</label>
        <select id="filter-status" onchange="refreshLogs()">
            <option value="all">全部</option>
            <option value="online">在线/开放</option>
            <option value="offline">离线/关闭</option>
        </select>
    </div>
    <div id="log-list-area">
        <div class="empty-state"><div class="icon">📭</div><p>暂无日志</p></div>
    </div>
</div>
</div>
<div class="footer">局域网运维监控工具 | Python + Flask | 轻量化单文件部署</div>
<script src="https://cdn.bootcdn.net/ajax/libs/jquery/3.6.0/jquery.min.js"></script>
<script>
$('#navbar a[data-page="logs"]').addClass('active');
function refreshLogs() {
    var type = $('#filter-type').val(), status = $('#filter-status').val();
    $.get('/api/logs', {type:type, status:status}, function(data) {
        $('#log-count').text(data.length);
        var html = '';
        if (data.length === 0) {
            html = '<div class="empty-state"><div class="icon">📭</div><p>暂无匹配的日志记录</p></div>';
        } else {
            html = '<table><thead><tr><th>时间</th><th>类型</th><th>名称</th><th>IP</th><th>端口</th><th>状态</th><th>详情</th></tr></thead><tbody>';
            for (var i = data.length - 1; i >= 0; i--) {
                var log = data[i];
                var typeCls = log.type === 'device' ? 'badge-info' : 'badge-warning';
                var typeText = log.type === 'device' ? '设备' : '服务';
                var isGood = log.status === 'online' || log.status === 'open';
                var stCls = isGood ? 'badge-success' : 'badge-danger';
                var stText = log.status;
                if (stText === 'online') stText = '在线';
                if (stText === 'offline') stText = '离线';
                if (stText === 'open') stText = '端口开放';
                if (stText === 'closed') stText = '端口关闭';
                html += '<tr><td class="text-muted">' + log.time + '</td>' +
                    '<td><span class="badge ' + typeCls + '">' + typeText + '</span></td>' +
                    '<td><strong>' + log.name + '</strong></td>' +
                    '<td>' + log.ip + '</td><td>' + (log.port || '-') + '</td>' +
                    '<td><span class="badge ' + stCls + '">' + stText + '</span></td>' +
                    '<td class="text-muted">' + (log.detail || '-') + '</td></tr>';
            }
            html += '</tbody></table>';
        }
        $('#log-list-area').html(html);
    });
}
refreshLogs();
function clearLogs() {
    if (!confirm('确定清空所有日志？')) return;
    $.post('/api/logs/clear', function() { refreshLogs(); });
}
</script>
</body>
</html>"""


# --- 设置页面（使用 Jinja2 变量）---
SETTINGS_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>设置 - 局域网运维监控工具</title>
<style>""" + COMMON_CSS + r"""</style>
</head>
<body>
<div class="header">
    <h1>🖥️ 局域网运维监控工具</h1>
    <div class="nav" id="navbar">
        <a href="/" data-page="dashboard">📊 仪表盘</a>
        <a href="/devices" data-page="devices">🔍 设备管理</a>
        <a href="/services" data-page="services">🔌 服务管理</a>
        <a href="/logs" data-page="logs">📋 日志查看</a>
        <a href="/settings" data-page="settings">⚙️ 设置</a>
    </div>
</div>
<div class="container">
<h2 style="margin-bottom:16px;">⚙️ 设置</h2>
<div class="card">
    <h2>⏱️ 自动巡检设置</h2>
    <div class="form-group" style="margin-bottom:16px;">
        <label for="interval">巡检间隔（秒）</label>
        <input type="number" id="interval" value="{{ interval }}" min="10" max="3600">
    </div>
    <button class="btn btn-primary" onclick="saveInterval()">💾 保存设置</button>
    <span class="text-muted" style="margin-left:10px;">
        当前自动巡检: {{ '运行中' if auto_scan else '已停止' }}
    </span>
</div>
<div class="card">
    <h2>ℹ️ 关于本工具</h2>
    <table>
        <tr><td><strong>工具名称</strong></td><td>局域网运维监控工具</td></tr>
        <tr><td><strong>技术栈</strong></td><td>Python 3 + Flask</td></tr>
        <tr><td><strong>日志文件</strong></td><td>{{ log_file }}</td></tr>
        <tr><td><strong>数据文件</strong></td><td>{{ data_file }}</td></tr>
        <tr><td><strong>设计特点</strong></td><td>单文件部署、无需数据库、无需登录、轻量化</td></tr>
    </table>
</div>
</div>
<div class="footer">局域网运维监控工具 | Python + Flask | 轻量化单文件部署</div>
<script src="https://cdn.bootcdn.net/ajax/libs/jquery/3.6.0/jquery.min.js"></script>
<script>
$('#navbar a[data-page="settings"]').addClass('active');
function saveInterval() {
    var v = parseInt($('#interval').val());
    if (isNaN(v) || v < 10) { alert('间隔不能少于10秒'); return; }
    $.post('/api/settings/interval', {interval:v}, function(d) {
        if (d.success) { alert('设置已保存'); location.reload(); }
        else { alert(d.message); }
    });
}
</script>
</body>
</html>"""


# ============================================================
# 工具函数
# ============================================================

def get_timestamp():
    """获取当前时间字符串"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _gen_id(prefix="item"):
    """生成唯一短ID"""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def ping_ip(ip):
    """
    使用系统 ping 命令检测 IP 是否在线
    返回: (是否在线, 延迟ms或错误信息)
    兼容 Windows / Linux / macOS
    """
    system = platform.system().lower()
    if system == "windows":
        cmd = ["ping", "-n", "1", "-w", "2000", ip]
    else:
        cmd = ["ping", "-c", "1", "-W", "2", ip]

    try:
        startupinfo = None
        if system == "windows":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            startupinfo=startupinfo,
            encoding='gbk' if system == "windows" else 'utf-8',
            errors='ignore'
        )

        output = result.stdout
        if result.returncode == 0:
            delay = "N/A"
            if system == "windows":
                m = re.search(r'平均\s*=\s*(\d+)ms', output)
                if not m:
                    m = re.search(r'time[=<]\s*(\d+)ms', output)
                if m:
                    delay = f"{m.group(1)}ms"
            else:
                m = re.search(r'time=([\d.]+)\s*ms', output)
                if m:
                    delay = f"{m.group(1)}ms"
            return True, delay
        else:
            return False, "请求超时"
    except subprocess.TimeoutExpired:
        return False, "请求超时"
    except Exception as e:
        return False, str(e)


def check_port(ip, port, timeout=3):
    """
    检测指定 IP 的端口是否开放
    返回: (是否开放, 描述信息)
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        result = sock.connect_ex((ip, int(port)))
        if result == 0:
            return True, "端口开放"
        else:
            return False, f"端口关闭 (错误码: {result})"
    except socket.timeout:
        return False, "连接超时"
    except socket.gaierror:
        return False, "地址解析失败"
    except Exception as e:
        return False, str(e)
    finally:
        sock.close()


def add_log(log_type, name, ip, status, detail="", port=None):
    """添加一条日志记录"""
    entry = {
        "time": get_timestamp(),
        "type": log_type,
        "name": name,
        "ip": ip,
        "status": status,
        "detail": detail
    }
    if port is not None:
        entry["port"] = port

    with data_lock:
        logs.append(entry)
        if len(logs) > 1000:
            logs[:] = logs[-1000:]


def save_logs():
    """将日志保存到 JSON 文件"""
    try:
        with data_lock:
            with open(LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[错误] 保存日志失败: {e}")


def save_data():
    """将配置保存到 JSON 文件"""
    try:
        data = {
            "devices": devices,
            "services": services,
            "auto_scan_interval": auto_scan_interval
        }
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[错误] 保存数据失败: {e}")


def load_data():
    """从 JSON 文件加载配置"""
    global devices, services, auto_scan_interval
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            devices = data.get("devices", [])
            services = data.get("services", [])
            auto_scan_interval = data.get("auto_scan_interval", 60)
            print(f"[信息] 已加载 {len(devices)} 个设备和 {len(services)} 个服务")
        except Exception as e:
            print(f"[错误] 加载数据失败: {e}")


def load_logs():
    """从 JSON 文件加载历史日志"""
    global logs
    if LOG_FILE.exists():
        try:
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                logs = json.load(f)
            print(f"[信息] 已加载 {len(logs)} 条历史日志")
        except Exception as e:
            print(f"[错误] 加载日志失败: {e}")


# ============================================================
# 核心巡检逻辑
# ============================================================

def scan_all_devices():
    """多线程批量扫描所有设备"""
    errors = []
    threads = []

    def worker(d):
        online, detail = ping_ip(d["ip"])
        now = get_timestamp()
        with data_lock:
            new_status = "online" if online else "offline"
            d["status"] = new_status
            d["last_check"] = now
            # 记录/清除故障开始时间
            if new_status == "offline" and d.get("failure_since") is None:
                d["failure_since"] = now
            elif new_status == "online":
                d["failure_since"] = None
        add_log("device", d["name"], d["ip"], "online" if online else "offline", detail)

    for d in devices:
        t = threading.Thread(target=worker, args=(d,), daemon=True)
        threads.append(t)
        t.start()
    for t in threads:
        t.join(timeout=10)


def scan_all_services():
    """多线程批量扫描所有服务端口"""
    threads = []

    def worker(s):
        ok, detail = check_port(s["ip"], s["port"])
        now = get_timestamp()
        with data_lock:
            new_status = "open" if ok else "closed"
            s["status"] = new_status
            s["last_check"] = now
            # 记录/清除故障开始时间
            if new_status == "closed" and s.get("failure_since") is None:
                s["failure_since"] = now
            elif new_status == "open":
                s["failure_since"] = None
        add_log("service", s["name"], s["ip"], "open" if ok else "closed", detail, port=s["port"])

    for s in services:
        t = threading.Thread(target=worker, args=(s,), daemon=True)
        threads.append(t)
        t.start()
    for t in threads:
        t.join(timeout=10)


def run_full_scan():
    """执行完整的设备+服务巡检"""
    scan_all_devices()
    scan_all_services()
    save_logs()
    save_data()


def auto_scan_loop():
    """自动巡检循环（后台线程运行）"""
    while auto_scan_enabled:
        print(f"[自动巡检] 开始扫描... ({get_timestamp()})")
        run_full_scan()
        print(f"[自动巡检] 扫描完成，下次间隔: {auto_scan_interval}秒")
        for _ in range(auto_scan_interval):
            if not auto_scan_enabled:
                break
            time.sleep(1)


# ============================================================
# Flask 页面路由
# ============================================================

@app.route('/')
def dashboard():
    """仪表盘"""
    return render_template_string(DASHBOARD_HTML)


@app.route('/devices')
def devices_page():
    """设备管理"""
    return render_template_string(DEVICES_HTML)


@app.route('/services')
def services_page():
    """服务管理"""
    return render_template_string(SERVICES_HTML)


@app.route('/logs')
def logs_page():
    """日志查看"""
    return render_template_string(LOGS_HTML)


@app.route('/settings')
def settings_page():
    """设置（使用 Jinja2 变量渲染）"""
    return render_template_string(
        SETTINGS_HTML,
        interval=auto_scan_interval,
        auto_scan=auto_scan_enabled,
        log_file=str(LOG_FILE),
        data_file=str(DATA_FILE)
    )


# ============================================================
# 仪表盘 API
# ============================================================

@app.route('/api/status')
def api_status():
    """获取仪表盘整体状态"""
    with data_lock:
        dev_list = [dict(d) for d in devices]
        svc_list = [dict(s) for s in services]

    online = sum(1 for d in dev_list if d["status"] == "online")
    offline = sum(1 for d in dev_list if d["status"] == "offline")
    opened = sum(1 for s in svc_list if s["status"] == "open")
    closed = sum(1 for s in svc_list if s["status"] == "closed")

    alerts = []
    for d in dev_list:
        if d["status"] == "offline":
            alerts.append(f"设备 [{d['name']}] ({d['ip']}) 离线")
    for s in svc_list:
        if s["status"] == "closed":
            alerts.append(f"服务 [{s['name']}] ({s['ip']}:{s['port']}) 端口关闭")

    return jsonify({
        "stats": {"online": online, "offline": offline, "open": opened, "closed": closed},
        "alerts": alerts,
        "devices": dev_list,
        "services": svc_list,
        "auto_scan": auto_scan_enabled
    })


@app.route('/api/scan')
def api_scan():
    """手动触发完整巡检"""
    run_full_scan()
    return jsonify({"success": True})


@app.route('/api/auto-scan/toggle', methods=['POST'])
def api_toggle_auto_scan():
    """开关自动巡检"""
    global auto_scan_enabled, auto_scan_thread
    auto_scan_enabled = not auto_scan_enabled
    if auto_scan_enabled:
        auto_scan_thread = threading.Thread(target=auto_scan_loop, daemon=True)
        auto_scan_thread.start()
    return jsonify({"success": True, "enabled": auto_scan_enabled})


# ============================================================
# 设备管理 API
# ============================================================

@app.route('/api/devices')
def api_get_devices():
    with data_lock:
        return jsonify([dict(d) for d in devices])


@app.route('/api/devices', methods=['POST'])
def api_add_device():
    name = request.form.get('name', '').strip()
    ip = request.form.get('ip', '').strip()
    if not name or not ip:
        return jsonify({"success": False, "message": "名称和IP不能为空"})
    parts = ip.split('.')
    if len(parts) != 4:
        return jsonify({"success": False, "message": "IP格式不正确"})
    with data_lock:
        if any(d["ip"] == ip for d in devices):
            return jsonify({"success": False, "message": f"IP {ip} 已存在"})
        device = {"id": _gen_id("dev"), "name": name, "ip": ip, "status": "unknown", "last_check": None, "failure_since": None}
        devices.append(device)
    save_data()
    return jsonify({"success": True, "device": device})


@app.route('/api/devices/batch', methods=['POST'])
def api_batch_add_devices():
    start = request.form.get('start', '').strip()
    end = request.form.get('end', '').strip()
    if not start or not end:
        return jsonify({"success": False, "message": "请填写起止IP"})
    try:
        sp = start.split('.')
        ep = end.split('.')
        if len(sp) != 4 or len(ep) != 4:
            return jsonify({"success": False, "message": "IP格式不正确"})
        prefix = '.'.join(sp[:3])
        if prefix != '.'.join(ep[:3]):
            return jsonify({"success": False, "message": "起止IP前3段必须相同（同网段）"})
        sn = int(sp[3])
        en = int(ep[3])
        if sn > en:
            return jsonify({"success": False, "message": "起始IP应小于等于结束IP"})
        if en > 254 or sn < 1:
            return jsonify({"success": False, "message": "IP范围应在 1-254"})
        count = 0
        with data_lock:
            existing = {d["ip"] for d in devices}
            for n in range(sn, en + 1):
                ip = f"{prefix}.{n}"
                if ip not in existing:
                    devices.append({"id": _gen_id("dev"), "name": f"设备-{n}", "ip": ip, "status": "unknown", "last_check": None, "failure_since": None})
                    count += 1
        save_data()
        return jsonify({"success": True, "count": count})
    except (ValueError, IndexError):
        return jsonify({"success": False, "message": "IP解析失败"})


@app.route('/api/devices/delete', methods=['POST'])
def api_delete_device():
    did = request.form.get('id', '')
    with data_lock:
        global devices
        before = len(devices)
        devices = [d for d in devices if d["id"] != did]
        if len(devices) == before:
            return jsonify({"success": False, "message": "设备不存在"})
    save_data()
    return jsonify({"success": True})


@app.route('/api/devices/clear', methods=['POST'])
def api_clear_devices():
    global devices
    with data_lock:
        devices = []
    save_data()
    return jsonify({"success": True})


@app.route('/api/scan/devices')
def api_scan_devices():
    scan_all_devices()
    save_logs()
    save_data()
    return jsonify({"success": True})


@app.route('/api/scan/device/<device_id>')
def api_scan_one_device(device_id):
    with data_lock:
        d = next((d for d in devices if d["id"] == device_id), None)
    if not d:
        return jsonify({"success": False, "message": "设备不存在"})
    online, detail = ping_ip(d["ip"])
    now = get_timestamp()
    with data_lock:
        new_status = "online" if online else "offline"
        d["status"] = new_status
        d["last_check"] = now
        if new_status == "offline" and d.get("failure_since") is None:
            d["failure_since"] = now
        elif new_status == "online":
            d["failure_since"] = None
    add_log("device", d["name"], d["ip"], "online" if online else "offline", detail)
    save_logs()
    save_data()
    return jsonify({"success": True, "status": d["status"], "detail": detail})


# ============================================================
# 服务管理 API
# ============================================================

@app.route('/api/services')
def api_get_services():
    with data_lock:
        return jsonify([dict(s) for s in services])


@app.route('/api/services', methods=['POST'])
def api_add_service():
    name = request.form.get('name', '').strip()
    ip = request.form.get('ip', '').strip()
    port = request.form.get('port', '').strip()
    if not name or not ip or not port:
        return jsonify({"success": False, "message": "参数不完整"})
    try:
        port = int(port)
        if port < 1 or port > 65535:
            return jsonify({"success": False, "message": "端口范围 1-65535"})
    except ValueError:
        return jsonify({"success": False, "message": "端口号必须为数字"})
    with data_lock:
        svc = {"id": _gen_id("svc"), "name": name, "ip": ip, "port": port, "status": "unknown", "last_check": None, "failure_since": None}
        services.append(svc)
    save_data()
    return jsonify({"success": True, "service": svc})


@app.route('/api/services/quick', methods=['POST'])
def api_quick_add_services():
    ip = request.form.get('ip', '').strip()
    if not ip:
        return jsonify({"success": False, "message": "请填写IP地址"})
    common = [
        (21, "FTP"), (22, "SSH"), (80, "HTTP"), (443, "HTTPS"),
        (3389, "RDP"), (3306, "MySQL"), (5432, "PostgreSQL"),
        (6379, "Redis"), (8080, "HTTP备用"),
    ]
    count = 0
    with data_lock:
        for port, pname in common:
            if not any(s["ip"] == ip and s["port"] == port for s in services):
                services.append({
                    "id": _gen_id("svc"), "name": f"{ip}-{pname}",
                    "ip": ip, "port": port, "status": "unknown", "last_check": None, "failure_since": None
                })
                count += 1
    save_data()
    return jsonify({"success": True, "count": count})


@app.route('/api/services/delete', methods=['POST'])
def api_delete_service():
    sid = request.form.get('id', '')
    with data_lock:
        global services
        before = len(services)
        services = [s for s in services if s["id"] != sid]
        if len(services) == before:
            return jsonify({"success": False, "message": "服务不存在"})
    save_data()
    return jsonify({"success": True})


@app.route('/api/services/clear', methods=['POST'])
def api_clear_services():
    global services
    with data_lock:
        services = []
    save_data()
    return jsonify({"success": True})


@app.route('/api/scan/services')
def api_scan_services():
    scan_all_services()
    save_logs()
    save_data()
    return jsonify({"success": True})


@app.route('/api/scan/service/<svc_id>')
def api_scan_one_service(svc_id):
    with data_lock:
        s = next((s for s in services if s["id"] == svc_id), None)
    if not s:
        return jsonify({"success": False, "message": "服务不存在"})
    ok, detail = check_port(s["ip"], s["port"])
    now = get_timestamp()
    with data_lock:
        new_status = "open" if ok else "closed"
        s["status"] = new_status
        s["last_check"] = now
        if new_status == "closed" and s.get("failure_since") is None:
            s["failure_since"] = now
        elif new_status == "open":
            s["failure_since"] = None
    add_log("service", s["name"], s["ip"], "open" if ok else "closed", detail, port=s["port"])
    save_logs()
    save_data()
    return jsonify({"success": True, "status": s["status"], "detail": detail})


# ============================================================
# 日志 API
# ============================================================

@app.route('/api/logs')
def api_get_logs():
    log_type = request.args.get('type', 'all')
    log_status = request.args.get('status', 'all')
    with data_lock:
        result = list(logs)
    if log_type != 'all':
        result = [l for l in result if l["type"] == log_type]
    if log_status == 'online':
        result = [l for l in result if l["status"] in ("online", "open")]
    elif log_status == 'offline':
        result = [l for l in result if l["status"] in ("offline", "closed")]
    return jsonify(result)


@app.route('/api/logs/clear', methods=['POST'])
def api_clear_logs():
    global logs
    with data_lock:
        logs = []
    if LOG_FILE.exists():
        os.remove(LOG_FILE)
    return jsonify({"success": True})


@app.route('/api/logs/export')
def api_export_logs():
    with data_lock:
        data = json.dumps(logs, ensure_ascii=False, indent=2)
    filename = f'lan_monitor_log_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    return Response(
        data,
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@app.route('/api/export/csv')
def api_export_csv():
    """导出当前设备和服务状态为 CSV 报告"""
    import csv
    import io

    with data_lock:
        dev_list = [dict(d) for d in devices]
        svc_list = [dict(s) for s in services]

    output = io.StringIO()
    writer = csv.writer(output)

    # 写入标题
    writer.writerow(["=== 局域网运维巡检报告 ==="])
    writer.writerow([f"生成时间: {get_timestamp()}"])
    writer.writerow([])

    # 设备部分
    writer.writerow(["【设备状态】"])
    if dev_list:
        writer.writerow(["设备名称", "IP地址", "状态", "故障持续", "延迟/详情", "最近检测时间"])
        for d in dev_list:
            status_text = "在线" if d["status"] == "online" else ("离线" if d["status"] == "offline" else "未检测")
            # 计算故障持续时长
            duration = ""
            if d["status"] == "offline" and d.get("failure_since"):
                try:
                    fs = datetime.strptime(d["failure_since"], "%Y-%m-%d %H:%M:%S")
                    diff = datetime.now() - fs
                    total_sec = int(diff.total_seconds())
                    if total_sec < 60:
                        duration = f"{total_sec}秒"
                    elif total_sec < 3600:
                        duration = f"{total_sec // 60}分{total_sec % 60}秒"
                    else:
                        h = total_sec // 3600
                        m = (total_sec % 3600) // 60
                        s = total_sec % 60
                        duration = f"{h}时{m}分{s}秒"
                except Exception:
                    duration = "N/A"
            else:
                duration = "-"
            writer.writerow([d["name"], d["ip"], status_text, duration, d.get("detail", ""), d.get("last_check", "")])
    else:
        writer.writerow(["(无设备)"])

    writer.writerow([])

    # 服务部分
    writer.writerow(["【服务端口状态】"])
    if svc_list:
        writer.writerow(["服务名称", "IP地址", "端口", "状态", "故障持续", "详情", "最近检测时间"])
        for s in svc_list:
            status_text = "开放" if s["status"] == "open" else ("关闭" if s["status"] == "closed" else "未检测")
            duration = ""
            if s["status"] == "closed" and s.get("failure_since"):
                try:
                    fs = datetime.strptime(s["failure_since"], "%Y-%m-%d %H:%M:%S")
                    diff = datetime.now() - fs
                    total_sec = int(diff.total_seconds())
                    if total_sec < 60:
                        duration = f"{total_sec}秒"
                    elif total_sec < 3600:
                        duration = f"{total_sec // 60}分{total_sec % 60}秒"
                    else:
                        h = total_sec // 3600
                        m = (total_sec % 3600) // 60
                        s = total_sec % 60
                        duration = f"{h}时{m}分{s}秒"
                except Exception:
                    duration = "N/A"
            else:
                duration = "-"
            writer.writerow([s["name"], s["ip"], s["port"], status_text, duration, s.get("detail", ""), s.get("last_check", "")])
    else:
        writer.writerow(["(无服务)"])

    writer.writerow([])

    # 统计汇总
    online_count = sum(1 for d in dev_list if d["status"] == "online")
    offline_count = sum(1 for d in dev_list if d["status"] == "offline")
    open_count = sum(1 for s in svc_list if s["status"] == "open")
    closed_count = sum(1 for s in svc_list if s["status"] == "closed")
    writer.writerow(["【统计汇总】"])
    writer.writerow(["设备在线", online_count, "设备离线", offline_count])
    writer.writerow(["服务端口开放", open_count, "服务端口关闭", closed_count])

    csv_content = output.getvalue()
    output.close()

    # BOM for Excel 正确识别中文 (utf-8-sig 自动添加 BOM)
    csv_bytes = csv_content.encode('utf-8-sig')

    filename = f'lan_monitor_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    return Response(
        csv_bytes,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


# ============================================================
# 设置 API
# ============================================================

@app.route('/api/settings/interval', methods=['POST'])
def api_set_interval():
    global auto_scan_interval
    try:
        v = int(request.form.get('interval', '60'))
        if v < 10:
            return jsonify({"success": False, "message": "间隔不能少于10秒"})
        if v > 3600:
            return jsonify({"success": False, "message": "间隔不能超过3600秒"})
        auto_scan_interval = v
        save_data()
        return jsonify({"success": True})
    except ValueError:
        return jsonify({"success": False, "message": "请输入有效数字"})


# ============================================================
# 启动入口
# ============================================================

def main():
    """程序启动"""
    print("=" * 60)
    print("   🖥️  局域网轻量化运维监控工具")
    print("   基于 Python + Flask 开发")
    print("=" * 60)

    load_data()
    load_logs()

    print(f"\n📡 数据文件: {DATA_FILE}")
    print(f"📋 日志文件: {LOG_FILE}")
    print(f"📊 已加载 {len(devices)} 个设备, {len(services)} 个服务, {len(logs)} 条日志")

    # 获取本机局域网 IP
    local_ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    print(f"\n🌐 访问地址:")
    print(f"   本机: http://127.0.0.1:5000")
    if local_ip != "127.0.0.1":
        print(f"   局域网: http://{local_ip}:5000")
    print(f"\n💡 按 Ctrl+C 停止服务\n")

    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)


if __name__ == '__main__':
    main()
