"""
FastAPI 应用入口。

当前提供能力：
1. /health 健康检查
2. /overview/live-rooms 获取各直播间概览（便于前端展示排名）
3. /danmu/jingjiu 获取中国劲酒最近的弹幕
4. /metrics/history 获取单个直播间的历史指标（用于前端趋势对比）

同时在应用启动时：
- 自动创建数据库表（开发阶段）
- 可选启动后台爬虫任务（使用模拟数据）
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import List

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from . import crud, database, schemas
from .crawler import tasks as crawler_tasks
from .crawler.douyin_client import DouyinLiveClient


def _as_utc(dt: datetime) -> datetime:
    """
    将数据库中的时间统一视为 UTC，并在返回给前端时显式带上时区信息。

    说明：
    - ORM 模型中的 created_at 默认使用 datetime.utcnow（无时区信息）
    - 如果直接序列化为 ISO 字符串（例如 "2025-01-01T06:42:05"），
      浏览器在解析时往往会把它当成本地时间，从而产生 8 小时偏差
    - 这里统一把“无 tz 的时间”视为 UTC，再加上 tzinfo=timezone.utc，
      前端收到带 "+00:00" / "Z" 的时间后，用 toLocaleTimeString 展示就会是本地时间
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


app = FastAPI(title="JJ Douyin Live Monitor", version="0.1.0")


@app.on_event("startup")
async def on_startup() -> None:
    """应用启动时执行的初始化逻辑。"""
    # 初始化数据库（开发阶段使用；生产环境建议使用 Alembic）
    await database.init_db()

    # 启动后台爬虫任务（当前写入模拟数据）
    if settings.enable_background_crawler:
        asyncio.create_task(crawler_tasks.run_crawler_loop(database.AsyncSessionLocal))


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    """
    项目演示首页。

    功能：
    1. 展示各酒类直播间人气排行榜与核心指标
    2. 展示中国劲酒直播间最近的弹幕列表

    说明：
    - 前端逻辑在浏览器中通过 JS 调用本服务的 API 完成
    - 主要依赖接口：
      * GET /overview/live-rooms
      * GET /danmu/jingjiu
    """
    return OLD_INDEX_HTML

OLD_INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <title>酒类直播监控雷达盘</title>
    <!-- 轻量使用 ECharts 做可视化展示（通过 CDN 引入） -->
    <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
    <!-- 添加更多视觉效果库 -->
    <script src="https://cdn.jsdelivr.net/npm/countup.js@2/dist/countUp.umd.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
      /* macOS Light Mode - Apple HIG */
      :root {
        --apple-blue: #007AFF;
        --apple-green: #34C759;
        --apple-orange: #FF9500;
        --apple-red: #FF3B30;
        --apple-purple: #5856D6;
        --apple-gray: #86868b;
        --apple-bg: #f5f5f7;
        --apple-card: rgba(255, 255, 255, 0.8);
        --apple-border: rgba(0, 0, 0, 0.06);
        --apple-text: #1d1d1f;
        --apple-text-secondary: #86868b;
      }

      body {
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Inter", system-ui, sans-serif;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
        margin: 0;
        padding: 24px;
        background: var(--apple-bg);
        color: var(--apple-text);
        min-height: 100vh;
        position: relative;
        overflow-x: hidden;
      }

      /* 微妙噪点纹理 */
      body::before {
        content: '';
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E");
        opacity: 0.015;
        pointer-events: none;
        z-index: -1;
      }

      .page-container {
        max-width: 1400px;
        margin: 0 auto;
        position: relative;
        z-index: 1;
      }

      .page-header {
        margin-bottom: 24px;
        text-align: center;
        position: relative;
      }

      .title-row {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 12px;
        margin-bottom: 12px;
      }

      .title-main {
        font-size: 28px;
        font-weight: 600;
        letter-spacing: -0.5px;
        color: var(--apple-text);
      }

      .title-main i {
        color: var(--apple-blue);
        margin-right: 8px;
      }

      .title-badge {
        font-size: 11px;
        padding: 4px 10px;
        border-radius: 6px;
        background: var(--apple-blue);
        color: #fff;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        white-space: nowrap;
      }

      .subtitle {
        font-size: 15px;
        color: var(--apple-text-secondary);
        margin-bottom: 12px;
        font-weight: 400;
      }

      .section {
        background: var(--apple-card);
        backdrop-filter: blur(20px) saturate(180%);
        -webkit-backdrop-filter: blur(20px) saturate(180%);
        padding: 20px;
        margin-bottom: 20px;
        border-radius: 12px;
        box-shadow:
          0 0 0 0.5px var(--apple-border),
          0 2px 8px rgba(0, 0, 0, 0.04),
          0 8px 24px rgba(0, 0, 0, 0.06),
          inset 0 1px 0 rgba(255, 255, 255, 0.6);
        position: relative;
        overflow: hidden;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
      }

      .section:hover {
        transform: translateY(-1px);
        box-shadow:
          0 0 0 0.5px var(--apple-border),
          0 4px 12px rgba(0, 0, 0, 0.06),
          0 12px 32px rgba(0, 0, 0, 0.08),
          inset 0 1px 0 rgba(255, 255, 255, 0.6);
      }

      .section-header {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 16px;
        position: relative;
      }

      .section-title {
        font-size: 17px;
        font-weight: 600;
        color: var(--apple-text);
        display: flex;
        align-items: center;
        gap: 8px;
        letter-spacing: -0.2px;
      }

      .section-title i {
        color: var(--apple-blue);
        font-size: 16px;
      }

      .section-subtitle {
        font-size: 13px;
        color: var(--apple-text-secondary);
        font-weight: 400;
      }

      .stats-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 12px;
        margin-bottom: 16px;
      }

      .stat-card {
        background: rgba(255, 255, 255, 0.6);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border-radius: 10px;
        padding: 16px;
        text-align: center;
        transition: transform 0.15s ease, box-shadow 0.15s ease;
        position: relative;
        overflow: hidden;
        box-shadow:
          0 0 0 0.5px var(--apple-border),
          0 1px 3px rgba(0, 0, 0, 0.04),
          inset 0 1px 0 rgba(255, 255, 255, 0.8);
      }

      .stat-card:hover {
        transform: translateY(-2px) scale(1.01);
        box-shadow:
          0 0 0 0.5px var(--apple-border),
          0 4px 12px rgba(0, 0, 0, 0.08),
          inset 0 1px 0 rgba(255, 255, 255, 0.8);
      }

      .stat-value {
        font-size: 26px;
        font-weight: 600;
        color: var(--apple-text);
        margin-bottom: 4px;
        letter-spacing: -0.5px;
      }

      .stat-label {
        font-size: 12px;
        color: var(--apple-text-secondary);
        text-transform: uppercase;
        letter-spacing: 0.03em;
        font-weight: 500;
      }

      .stat-change {
        font-size: 11px;
        margin-top: 6px;
        font-weight: 500;
        color: var(--apple-text-secondary);
      }

      .stat-up {
        color: var(--apple-green);
        display: inline-flex;
        align-items: center;
        gap: 3px;
      }

      .stat-down {
        color: var(--apple-red);
        display: inline-flex;
        align-items: center;
        gap: 3px;
      }
      table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        margin-top: 12px;
        font-size: 13px;
        border-radius: 10px;
        overflow: hidden;
        background: rgba(255, 255, 255, 0.5);
        box-shadow: 0 0 0 0.5px var(--apple-border);
      }

      th, td {
        padding: 12px 14px;
        text-align: center;
        border-bottom: 0.5px solid var(--apple-border);
      }

      th {
        background: rgba(0, 0, 0, 0.02);
        color: var(--apple-text-secondary);
        font-weight: 500;
        text-transform: uppercase;
        font-size: 11px;
        letter-spacing: 0.03em;
        position: sticky;
        top: 0;
        z-index: 10;
      }

      td {
        background: transparent;
        color: var(--apple-text);
        transition: background 0.15s ease;
      }

      tr:last-child td {
        border-bottom: none;
      }

      tr:hover td {
        background: rgba(0, 122, 255, 0.04);
      }

      .live {
        color: #fff;
        background: var(--apple-green);
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 500;
        font-size: 11px;
      }

      .offline {
        color: var(--apple-text-secondary);
        padding: 4px 10px;
        border-radius: 6px;
        background: rgba(0, 0, 0, 0.04);
        font-size: 11px;
        font-weight: 500;
      }

      .danmu-list {
        list-style: none;
        padding: 0;
        max-height: 400px;
        overflow-y: auto;
        font-size: 13px;
        border-radius: 10px;
      }

      .danmu-item {
        padding: 12px 14px;
        margin-bottom: 6px;
        background: rgba(255, 255, 255, 0.5);
        border-left: 3px solid var(--apple-blue);
        border-radius: 8px;
        transition: background 0.15s ease, transform 0.15s ease;
        box-shadow: 0 0 0 0.5px var(--apple-border);
      }

      .danmu-item:hover {
        background: rgba(255, 255, 255, 0.8);
        transform: translateX(2px);
      }

      .danmu-nickname {
        font-weight: 600;
        color: var(--apple-blue);
        margin-right: 8px;
      }

      .danmu-time {
        color: var(--apple-text-secondary);
        font-size: 11px;
        margin-right: 10px;
        font-family: "SF Mono", "Menlo", monospace;
      }

      .footer {
        font-size: 12px;
        color: var(--apple-text-secondary);
        margin-top: 12px;
        text-align: center;
      }

      .summary {
        margin-top: 12px;
        font-size: 13px;
        color: var(--apple-text);
        background: rgba(0, 122, 255, 0.06);
        padding: 12px 16px;
        border-radius: 8px;
        border: 0.5px solid rgba(0, 122, 255, 0.15);
        text-align: center;
        font-weight: 500;
      }

      .delta-up {
        color: var(--apple-green);
        font-size: 11px;
        margin-left: 6px;
        font-weight: 600;
        display: inline-flex;
        align-items: center;
        gap: 2px;
      }

      .delta-down {
        color: var(--apple-red);
        font-size: 11px;
        margin-left: 6px;
        font-weight: 600;
        display: inline-flex;
        align-items: center;
        gap: 2px;
      }

      .charts-row {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
        gap: 16px;
        margin-top: 16px;
      }

      .chart-box {
        background: rgba(255, 255, 255, 0.6);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border-radius: 10px;
        padding: 16px;
        box-shadow:
          0 0 0 0.5px var(--apple-border),
          0 2px 8px rgba(0, 0, 0, 0.04),
          inset 0 1px 0 rgba(255, 255, 255, 0.8);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
        position: relative;
        overflow: hidden;
      }

      .chart-box:hover {
        transform: translateY(-2px);
        box-shadow:
          0 0 0 0.5px var(--apple-border),
          0 6px 16px rgba(0, 0, 0, 0.08),
          inset 0 1px 0 rgba(255, 255, 255, 0.8);
      }

      .chart-title {
        font-size: 14px;
        color: var(--apple-text);
        margin-bottom: 12px;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 8px;
        letter-spacing: -0.2px;
      }

      .chart-title i {
        color: var(--apple-blue);
        font-size: 13px;
      }

      .chart-canvas {
        width: 100%;
        height: 280px;
        border-radius: 6px;
      }

      .row-top1 {
        background: rgba(52, 199, 89, 0.08);
      }

      .row-top3 {
        background: rgba(0, 122, 255, 0.04);
      }

      .row-selected {
        box-shadow: inset 0 0 0 2px var(--apple-blue);
      }

      .room-link {
        color: var(--apple-blue);
        text-decoration: none;
        font-weight: 500;
        transition: opacity 0.15s ease;
        padding: 2px 4px;
        border-radius: 4px;
      }

      .room-link:hover {
        opacity: 0.7;
        text-decoration: none;
      }

      .realtime-indicator {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 10px;
        background: rgba(52, 199, 89, 0.1);
        border: 0.5px solid rgba(52, 199, 89, 0.3);
        border-radius: 6px;
        font-size: 11px;
        color: var(--apple-green);
        font-weight: 500;
      }

      .realtime-dot {
        width: 6px;
        height: 6px;
        background: var(--apple-green);
        border-radius: 50%;
        animation: dotPulse 2s ease-in-out infinite;
      }

      @keyframes dotPulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
      }

      /* 滚动条样式 - macOS 风格 */
      ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
      }

      ::-webkit-scrollbar-track {
        background: transparent;
      }

      ::-webkit-scrollbar-thumb {
        background: rgba(0, 0, 0, 0.2);
        border-radius: 4px;
      }

      ::-webkit-scrollbar-thumb:hover {
        background: rgba(0, 0, 0, 0.3);
      }

      .section-controls {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
        margin: 8px 0 4px 0;
        flex-wrap: wrap;
      }

      .filter-group,
      .refresh-group {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 12px;
        color: var(--apple-text-secondary);
      }

      .toggle-button {
        border-radius: 6px;
        border: 0.5px solid var(--apple-border);
        background: rgba(255, 255, 255, 0.6);
        color: var(--apple-text);
        padding: 6px 12px;
        font-size: 12px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.15s ease;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
      }

      .toggle-button:hover {
        background: rgba(255, 255, 255, 0.9);
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.06);
      }

      .toggle-button:active {
        transform: scale(0.97);
      }

      .toggle-button.active {
        background: var(--apple-blue);
        border-color: var(--apple-blue);
        color: #fff;
        box-shadow: 0 1px 3px rgba(0, 122, 255, 0.3);
      }

      .recheck-button {
        margin-left: 8px;
        padding: 4px 10px;
        font-size: 11px;
      }

      .recheck-tooltip {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        margin-left: 6px;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 11px;
        border: 0.5px solid var(--apple-border);
        background: rgba(255, 255, 255, 0.9);
        color: var(--apple-text);
        animation: fadeInOut 3s ease-in-out forwards;
      }

      .recheck-tooltip-ok {
        border-color: rgba(52, 199, 89, 0.4);
        background: rgba(52, 199, 89, 0.1);
        color: var(--apple-green);
      }

      .recheck-tooltip-warn {
        border-color: rgba(255, 149, 0, 0.4);
        background: rgba(255, 149, 0, 0.1);
        color: var(--apple-orange);
      }

      .recheck-tooltip-error {
        border-color: rgba(255, 59, 48, 0.4);
        background: rgba(255, 59, 48, 0.1);
        color: var(--apple-red);
      }

      @keyframes fadeInOut {
        0% { opacity: 0; transform: translateY(-2px); }
        10% { opacity: 1; transform: translateY(0); }
        80% { opacity: 1; transform: translateY(0); }
        100% { opacity: 0; transform: translateY(-2px); }
      }

      .danmu-summary {
        display: flex;
        flex-direction: column;
        gap: 8px;
        margin-bottom: 12px;
        padding: 12px 14px;
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.5);
        border: 0.5px solid var(--apple-border);
        font-size: 13px;
        color: var(--apple-text);
      }

      .keyword-tags {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-top: 4px;
      }

      .keyword-tag {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 3px 10px;
        border-radius: 6px;
        background: rgba(0, 122, 255, 0.08);
        border: 0.5px solid rgba(0, 122, 255, 0.2);
        font-size: 11px;
        color: var(--apple-blue);
        font-weight: 500;
      }

      .keyword-tag.muted {
        background: rgba(0, 0, 0, 0.03);
        border-color: var(--apple-border);
        color: var(--apple-text-secondary);
      }

      .keyword-count {
        background: rgba(0, 122, 255, 0.15);
        padding: 1px 6px;
        border-radius: 4px;
        font-weight: 600;
        color: var(--apple-blue);
      }

      /* 响应式设计 */
      @media (max-width: 768px) {
        body {
          padding: 16px;
        }

        .page-container {
          padding: 0;
        }

        .title-main {
          font-size: 22px;
        }

        .charts-row {
          grid-template-columns: 1fr;
          gap: 12px;
        }

        .stats-grid {
          grid-template-columns: 1fr 1fr;
        }

        .section {
          padding: 14px;
        }

        .section-controls {
          flex-direction: column;
          align-items: flex-start;
        }

        table {
          font-size: 12px;
        }

        th, td {
          padding: 10px 8px;
        }
      }
    </style>
  </head>
  <body>
    <div class="page-container">
      <header class="page-header">
        <div class="title-row">
          <h1 class="title-main">
            <i class="fas fa-chart-line"></i>
            酒类直播监控雷达盘
          </h1>
          <span class="title-badge">PORTFOLIO DEMO</span>
          <div class="realtime-indicator">
            <div class="realtime-dot"></div>
            实时监控中
          </div>
        </div>
        <div class="subtitle">实时洞察酒类品牌直播间的人气与互动，为运营决策提供数据支撑。</div>
        <div class="footer">
          <i class="fas fa-robot"></i> 数据来源：抖音直播间（Playwright 实时采集） |
          <i class="fas fa-bolt"></i> 后端：FastAPI + MySQL |
          <i class="fas fa-sync"></i> 页面每 5 秒自动刷新
        </div>
        <div class="summary" id="summary-bar">
          <i class="fas fa-spinner fa-spin"></i> 正在统计直播间数据，请稍候...
        </div>
      </header>

      <!-- 数据统计卡片 -->
      <div class="section">
        <div class="section-header">
          <h2 class="section-title">
            <i class="fas fa-tachometer-alt"></i>
            核心数据监控
          </h2>
          <span class="section-subtitle">实时统计数据与趋势分析</span>
        </div>
        <div class="stats-grid" id="stats-grid">
          <div class="stat-card">
            <div class="stat-value" id="total-rooms">-</div>
            <div class="stat-label">监控品牌总数</div>
            <div class="stat-change stat-up">
              <i class="fas fa-check-circle"></i> 运行正常
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-value" id="live-rooms">-</div>
            <div class="stat-label">当前直播中</div>
            <div class="stat-change" id="live-status">
              <i class="fas fa-circle"></i> 统计中
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-value" id="total-online">-</div>
            <div class="stat-label">总在线人数</div>
            <div class="stat-change" id="online-trend">
              <i class="fas fa-chart-line"></i> 计算中
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-value" id="total-likes">-</div>
            <div class="stat-label">总点赞数</div>
            <div class="stat-change" id="like-trend">
              <i class="fas fa-heart"></i> 汇总中
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-value" id="recent-danmu">-</div>
            <div class="stat-label">近期弹幕总数</div>
            <div class="stat-change stat-up">
              <i class="fas fa-comments"></i> 10分钟内
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-value" id="jingjiu-online">-</div>
            <div class="stat-label">中国劲酒 在线 / 点赞</div>
            <div class="stat-change" id="jingjiu-status">
              <i class="fas fa-wine-bottle"></i> 状态统计中
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-value" id="update-time">-</div>
            <div class="stat-label">最后更新时间</div>
            <div class="stat-change">
              <i class="fas fa-clock"></i> 实时更新
            </div>
          </div>
        </div>
      </div>

      <div class="section">
        <div class="section-header">
          <h2 class="section-title">
            <i class="fas fa-chart-bar"></i>
            一、全局数据洞察
          </h2>
          <span class="section-subtitle">当前在线人数 & 本场点赞的整体分布</span>
        </div>
        <div class="section-controls">
          <div class="filter-group">
            <i class="fas fa-filter"></i>
            <span>显示范围：</span>
            <button id="filter-all" class="toggle-button">
              全部直播间
            </button>
            <button id="filter-live" class="toggle-button active">
              仅直播中
            </button>
            <button id="filter-other" class="toggle-button">
              仅其他直播间
            </button>
          </div>
          <div class="refresh-group">
            <i class="fas fa-sync-alt"></i>
            <span>自动刷新：</span>
            <button id="refresh-toggle" class="toggle-button active">
              每 5 秒自动刷新
            </button>
            <button id="refresh-now" class="toggle-button">
              立即刷新
            </button>
          </div>
        </div>
        <div class="charts-row">
          <div class="chart-box">
            <div class="chart-title">
              <i class="fas fa-users"></i>
              在线人数分布（按直播间）
            </div>
            <div id="chart-online" class="chart-canvas"></div>
          </div>
          <div class="chart-box">
            <div class="chart-title">
              <i class="fas fa-heart"></i>
              本场点赞分布（按直播间）
            </div>
            <div id="chart-like" class="chart-canvas"></div>
          </div>
        </div>
      </div>

      <div class="section">
        <div class="section-header">
          <h2 class="section-title">
            <i class="fas fa-trophy"></i>
            二、酒类直播间人气排行榜
          </h2>
          <span class="section-subtitle">按在线人数与点赞综合排序，Top1 行高亮展示</span>
        </div>
      <table id="room-table">
        <thead>
          <tr>
            <th><i class="fas fa-medal"></i> 排名</th>
            <th><i class="fas fa-broadcast-tower"></i> 直播间名称</th>
            <th><i class="fas fa-users"></i> 当前在线人数</th>
            <th><i class="fas fa-heart"></i> 本场点赞</th>
            <th><i class="fas fa-video"></i> 状态</th>
            <th><i class="fas fa-comments"></i> 最近弹幕数（10 分钟）</th>
            <th><i class="fas fa-clock"></i> 最近更新时间</th>
          </tr>
        </thead>
        <tbody id="room-table-body">
          <tr>
            <td colspan="7">
              <i class="fas fa-spinner fa-spin"></i> 正在加载数据...
            </td>
          </tr>
        </tbody>
      </table>
      </div>

      <div class="section">
        <div class="section-header">
          <h2 class="section-title">
            <i class="fas fa-history"></i>
            三、历史趋势对比（单个直播间）
          </h2>
          <span class="section-subtitle">
            点击上方排行榜中的某个直播间，可查看最近一段时间的在线人数 / 点赞变化趋势
          </span>
        </div>
        <div id="history-summary" class="danmu-summary">
          <span>
            <i class="fas fa-info-circle"></i>
            请选择上方的某个直播间行，查看最近 60 分钟的历史数据变化。
          </span>
        </div>
        <div class="chart-box">
          <div class="chart-title">
            <i class="fas fa-chart-line"></i>
            <span id="history-chart-title">历史趋势图（最近 60 分钟）</span>
          </div>
          <div id="history-chart" class="chart-canvas"></div>
        </div>
      </div>

      <div class="section">
        <div class="section-header">
          <h2 class="section-title">
            <i class="fas fa-comments"></i>
            四、中国劲酒直播间实时弹幕
          </h2>
          <span class="section-subtitle">最近 10 分钟高频互动内容</span>
        </div>
        <div class="danmu-summary" id="danmu-summary">
          <span>
            <i class="fas fa-info-circle"></i>
            最近 10 分钟内，共 <strong id="danmu-total">-</strong> 条中国劲酒弹幕
          </span>
          <div class="keyword-tags" id="danmu-keywords">
            <span class="keyword-tag muted">正在分析热门关键词...</span>
          </div>
        </div>
        <ul id="danmu-list" class="danmu-list">
          <li><i class="fas fa-spinner fa-spin"></i> 正在加载弹幕...</li>
        </ul>
      </div>
    </div>

    <script>
      // 记录上一次的概览结果，用于做数据对比（例如在线人数、点赞数的涨跌）
      let lastOverview = null;
      let onlineChart = null;
      let likeChart = null;
      let historyChart = null;
      let countUpInstances = {};

      // 控制展示和刷新行为的状态
      let showOnlyLive = true;        // 是否只展示"直播中"的直播间（排行榜）
      let showOnlyOtherRooms = false; // 是否只展示"中国劲酒之外"的其他直播间
      let autoRefreshEnabled = true;  // 是否开启自动刷新
      let overviewTimer = null;       // 概览数据刷新定时器
      let historyTimer = null;        // 历史趋势刷新定时器

      // 历史趋势相关状态
      let selectedRoomName = null;    // 当前选中用于查看历史趋势的直播间
      const HISTORY_MINUTES = 60;     // 历史趋势时间窗口
      const OVERVIEW_INTERVAL = 5000; // 概览刷新间隔 (5s)
      const HISTORY_INTERVAL = 60000; // 历史刷新间隔 (60s)

      // 初始化 CountUp 实例
      function initCountUp(id, startVal, endVal, duration = 2) {
        if (countUpInstances[id]) {
          countUpInstances[id].update(endVal);
        } else {
          countUpInstances[id] = new countUp.CountUp(id, endVal, {
            startVal: startVal,
            duration: duration,
            useEasing: true,
            useGrouping: true,
            separator: ',',
            decimal: '.'
          });
          countUpInstances[id].start();
        }
      }

      async function fetchJson(url) {
        const resp = await fetch(url);
        if (!resp.ok) {
          throw new Error("请求失败: " + resp.status);
        }
        return await resp.json();
      }

      function formatTime(isoString) {
        if (!isoString) return "";
        const d = new Date(isoString);
        if (Number.isNaN(d.getTime())) return isoString;
        return d.toLocaleTimeString("zh-CN", { hour12: false });
      }

      function formatNumber(num) {
        if (num >= 1000000) {
          return (num / 1000000).toFixed(1) + 'M';
        } else if (num >= 1000) {
          return (num / 1000).toFixed(1) + 'K';
        }
        return num.toString();
      }

      function updateStatsCards(overview) {
        if (!overview || !overview.items) return;

        // 计算统计数据
        const totalRooms = overview.items.length;
        const liveRooms = overview.items.filter(item => item.latest_is_live).length;
        const totalOnline = overview.items
          .filter(item => item.latest_is_live)
          .reduce((sum, item) => sum + item.latest_online_count, 0);
        const totalLikes = overview.items
          .filter(item => item.latest_is_live)
          .reduce((sum, item) => sum + item.latest_like_count, 0);
        const recentDanmu = overview.items
          .reduce((sum, item) => sum + item.recent_danmu_count, 0);

        const latestUpdateTime = overview.items
          .filter(item => item.last_updated_at)
          .map(item => new Date(item.last_updated_at))
          .sort((a, b) => b - a)[0];

        // 定位中国劲酒直播间的最新数据
        const jingjiuItem = overview.items.find(item => item.room_name === "中国劲酒");

        // 使用 CountUp 动画更新数字
        initCountUp('total-rooms', 0, totalRooms, 1);
        initCountUp('live-rooms', 0, liveRooms, 1.5);
        initCountUp('total-online', 0, totalOnline, 2);
        initCountUp('total-likes', 0, totalLikes, 2.5);
        initCountUp('recent-danmu', 0, recentDanmu, 1.8);

        // 更新中国劲酒专属卡片
        const jingjiuValueEl = document.getElementById('jingjiu-online');
        const jingjiuStatusEl = document.getElementById('jingjiu-status');
        if (jingjiuValueEl && jingjiuStatusEl) {
          if (jingjiuItem) {
            const online = jingjiuItem.latest_online_count;
            const likes = jingjiuItem.latest_like_count;
            const danmuCount = jingjiuItem.recent_danmu_count || 0;
            jingjiuValueEl.textContent = `${formatNumber(online)} / ${formatNumber(likes)}`;

            if (jingjiuItem.latest_is_live) {
              jingjiuStatusEl.className = 'stat-change stat-up';
              jingjiuStatusEl.innerHTML = `
                <i class="fas fa-wine-bottle"></i> 中国劲酒 · 直播中
                <span style="margin-left:6px;font-size:11px;color:#bbf7d0;">
                  <i class="fas fa-comments"></i> 近 10 分钟弹幕 ${danmuCount} 条
                </span>
              `;
            } else {
              jingjiuStatusEl.className = 'stat-change stat-down';
              jingjiuStatusEl.innerHTML = `
                <i class="fas fa-wine-bottle"></i> 中国劲酒 · 未开播
              `;
            }
          } else {
            jingjiuValueEl.textContent = "-";
            jingjiuStatusEl.className = 'stat-change';
            jingjiuStatusEl.innerHTML = '<i class="fas fa-wine-bottle"></i> 暂未监控到中国劲酒数据';
          }
        }

        // 更新最后更新时间
        const updateTimeElement = document.getElementById('update-time');
        if (updateTimeElement && latestUpdateTime) {
          updateTimeElement.textContent = formatTime(latestUpdateTime.toISOString());
        }

        // 更新状态指示器
        const liveStatusElement = document.getElementById('live-status');
        if (liveStatusElement) {
          if (liveRooms > 0) {
            liveStatusElement.className = 'stat-change stat-up';
            liveStatusElement.innerHTML = `<i class="fas fa-circle"></i> ${liveRooms} 个直播间`;
          } else {
            liveStatusElement.className = 'stat-change stat-down';
            liveStatusElement.innerHTML = `<i class="fas fa-circle"></i> 暂无直播`;
          }
        }

        // 更新趋势指示器
        const onlineTrendElement = document.getElementById('online-trend');
        if (onlineTrendElement) {
          onlineTrendElement.className = totalOnline > 0 ? 'stat-change stat-up' : 'stat-change stat-down';
          onlineTrendElement.innerHTML = totalOnline > 0
            ? `<i class="fas fa-arrow-up"></i> 人气高涨`
            : `<i class="fas fa-arrow-down"></i> 数据统计中`;
        }
      }

      function renderRooms(overview) {
        const tbody = document.getElementById("room-table-body");
        const summaryBar = document.getElementById("summary-bar");
        tbody.innerHTML = "";

        // 首先更新统计卡片
        updateStatsCards(overview);

        if (!overview.items || overview.items.length === 0) {
          const tr = document.createElement("tr");
          const td = document.createElement("td");
          td.colSpan = 7;
          td.innerHTML = '<i class="fas fa-exclamation-circle"></i> 暂无数据';
          tr.appendChild(td);
          tbody.appendChild(tr);
          if (summaryBar) {
            summaryBar.innerHTML = '<i class="fas fa-exclamation-triangle"></i> 当前暂无直播数据。';
          }
          return;
        }

        // 上一次的数据，用于做对比：room_name -> item
        const prevMap = {};
        if (lastOverview && Array.isArray(lastOverview.items)) {
          lastOverview.items.forEach((item) => {
            prevMap[item.room_name] = item;
          });
        }

        // 汇总信息
        let totalOnline = 0;
        let liveCount = 0;
        let latestUpdateStr = null;
        let latestUpdateTime = null;

        // 根据当前筛选条件（是否仅展示直播中 / 是否仅展示其他直播间）过滤数据
        let items = overview.items.slice();
        if (showOnlyOtherRooms) {
          // 仅展示除“中国劲酒”之外的其他直播间，方便人工校验“其他直播间是否在直播”
          items = items.filter((item) => item.room_name !== "中国劲酒");
        }
        if (showOnlyLive) {
          items = items.filter((item) => item.latest_is_live);
        }

        // 如果原始数据存在，但在当前筛选条件下没有任何直播间，给出清晰提示，避免误以为“爬虫完全没数据”
        if (items.length === 0) {
          const tr = document.createElement("tr");
          const td = document.createElement("td");
          td.colSpan = 7;
          td.innerHTML = `
            <i class="fas fa-info-circle"></i>
            当前筛选条件下没有匹配的直播间数据，可能所有直播间当前都未开播。
            您可以尝试点击上方的 <strong>“全部直播间”</strong> 按钮查看最近一次记录，或稍后再试。
          `;
          tr.appendChild(td);
          tbody.appendChild(tr);

          if (summaryBar) {
            const latestUpdateTimeStr = overview.items
              .filter((item) => item.last_updated_at)
              .map((item) => item.last_updated_at)
              .sort()
              .slice(-1)[0] || null;
            const timeText = latestUpdateTimeStr ? formatTime(latestUpdateTimeStr) : "-";

            summaryBar.innerHTML = `
              <i class="fas fa-chart-line"></i>
              当前筛选条件下暂无直播中或符合条件的直播间 |
              最近一次采集时间：<strong>${timeText}</strong> |
              <span style="color:#9ca3af;font-size:12px;">
                <i class="fas fa-filter"></i> 建议切换到“全部直播间”查看原始数据
              </span>
            `;
          }

          // 同样保存本次结果，避免后续对比出现异常
          lastOverview = overview;

          // 图表仍然可以基于原始 overview 渲染，直观展示当前整体情况
          renderCharts(overview);
          return;
        }

        // 排名规则：正在直播优先，其次按在线人数降序，再按点赞数降序
        items = items.sort((a, b) => {
          if (a.latest_is_live !== b.latest_is_live) {
            return a.latest_is_live ? -1 : 1;
          }
          if (b.latest_online_count !== a.latest_online_count) {
            return b.latest_online_count - a.latest_online_count;
          }
          return b.latest_like_count - a.latest_like_count;
        });

        items.forEach((item, index) => {
          const tr = document.createElement("tr");

          if (item.latest_is_live) {
            if (index === 0) {
              tr.className = "row-top1";
            } else if (index < 3) {
              tr.className = "row-top3";
            }
          }

          // 排名列
          const rankTd = document.createElement("td");
          let rankContent = (index + 1).toString();
          if (index === 0 && item.latest_is_live) {
            rankContent = '👑 ' + rankContent;
          } else if (index < 3 && item.latest_is_live) {
            rankContent = ['🥇', '🥈', '🥉'][index] + ' ' + rankContent;
          }
          rankTd.innerHTML = `<strong>${rankContent}</strong>`;
          tr.appendChild(rankTd);

          // 直播间名称列
          const nameTd = document.createElement("td");
          const link = document.createElement("a");
          link.href = item.room_url;
          link.textContent = item.room_name;
          link.target = "_blank";
          link.className = "room-link";
          nameTd.appendChild(link);
          tr.appendChild(nameTd);

          // 在线人数列
          const onlineTd = document.createElement("td");
          const likeTd = document.createElement("td");
          const statusTd = document.createElement("td");

          if (item.latest_is_live) {
            // 当前在线人数 / 点赞
            onlineTd.textContent = formatNumber(item.latest_online_count);
            likeTd.textContent = formatNumber(item.latest_like_count);

            // 统计汇总
            totalOnline += item.latest_online_count;
            liveCount += 1;

            // 同一房间与上一次的数据对比（涨跌）
            const prev = prevMap[item.room_name];
            if (prev && prev.latest_is_live) {
              const deltaOnline = item.latest_online_count - prev.latest_online_count;
              const deltaLike = item.latest_like_count - prev.latest_like_count;

              if (deltaOnline !== 0) {
                const span = document.createElement("span");
                span.className = deltaOnline > 0 ? "delta-up" : "delta-down";
                span.innerHTML = (deltaOnline > 0 ? "↑" : "↓") + Math.abs(deltaOnline);
                onlineTd.appendChild(span);
              }

              if (deltaLike !== 0) {
                const span = document.createElement("span");
                span.className = deltaLike > 0 ? "delta-up" : "delta-down";
                span.innerHTML = (deltaLike > 0 ? "↑" : "↓") + Math.abs(deltaLike);
                likeTd.appendChild(span);
              }
            }

            const span = document.createElement("span");
            span.textContent = "直播中";
            span.className = "live";
            statusTd.appendChild(span);
          } else {
            // 未开播时，在界面上不展示具体数值，用短横线表示
            onlineTd.textContent = "-";
            likeTd.textContent = "-";

            const span = document.createElement("span");
            span.textContent = "未开播";
            span.className = "offline";
            statusTd.appendChild(span);

            // 为“未开播”行增加一个手动重查按钮，便于人工干预提升数据准确率
            const recheckBtn = document.createElement("button");
            recheckBtn.textContent = "重新检测";
            recheckBtn.className = "toggle-button recheck-button";
            recheckBtn.addEventListener("click", (event) => {
              // 避免触发展开历史趋势的行点击事件
              event.stopPropagation();
              manualRecheckRoom(item.room_name, recheckBtn);
            });
            statusTd.appendChild(recheckBtn);
          }

          tr.appendChild(onlineTd);
          tr.appendChild(likeTd);
          tr.appendChild(statusTd);

          // 弹幕数列
          const danmuCountTd = document.createElement("td");
          if (item.recent_danmu_count > 0) {
            danmuCountTd.innerHTML = `<strong>${item.recent_danmu_count}</strong>`;
          } else {
            danmuCountTd.textContent = "0";
          }
          tr.appendChild(danmuCountTd);

          // 时间列
          const timeTd = document.createElement("td");
          timeTd.textContent = formatTime(item.last_updated_at);
          tr.appendChild(timeTd);

          // 如果当前行对应“选中的直播间”，加一层高亮，便于用户知道正在看谁的历史趋势
          if (selectedRoomName && item.room_name === selectedRoomName) {
            tr.classList.add("row-selected");
          }

          // 点击任意一行，可切换历史趋势查看对象
          tr.addEventListener("click", () => {
            handleRoomRowClick(item.room_name, tr);
          });

          tbody.appendChild(tr);

          // 记录面板最近更新时间
          if (item.last_updated_at) {
            const t = new Date(item.last_updated_at);
            if (!Number.isNaN(t.getTime())) {
              if (!latestUpdateTime || t > latestUpdateTime) {
                latestUpdateTime = t;
                latestUpdateStr = item.last_updated_at;
              }
            }
          }
        });

        // 更新页面顶部汇总信息
        if (summaryBar) {
          const timeText = latestUpdateStr ? formatTime(latestUpdateStr) : "-";
          let rangeText = "展示全部直播间";
          if (showOnlyOtherRooms && showOnlyLive) {
            rangeText = "仅展示其他直播间（直播中）";
          } else if (showOnlyOtherRooms) {
            rangeText = "仅展示其他直播间";
          } else if (showOnlyLive) {
            rangeText = "仅展示直播中";
          }
          summaryBar.innerHTML = `
            <i class="fas fa-chart-line"></i> 当前直播中：<strong>${liveCount}</strong> 间 |
            总在线人数：<strong>${formatNumber(totalOnline)}</strong> |
            最近更新时间：<strong>${timeText}</strong> |
            <span style="color:#9ca3af;font-size:12px;"><i class="fas fa-filter"></i> ${rangeText}</span>
          `;
        }

        // 保存本次结果，用于下次做对比
        lastOverview = overview;

        // 同步更新图表展示
        renderCharts(overview);
      }

      async function loadHistoryForRoom(roomName, isAutoRefresh = false) {
        const summaryEl = document.getElementById("history-summary");
        const titleEl = document.getElementById("history-chart-title");

        if (!roomName) return;

        selectedRoomName = roomName;

        if (titleEl) {
          titleEl.textContent = `历史趋势图（${roomName}，最近 ${HISTORY_MINUTES} 分钟）`;
        }

        if (summaryEl && !isAutoRefresh) {
          summaryEl.innerHTML = `
            <span>
              <i class="fas fa-spinner fa-spin"></i>
              正在加载 <strong>${roomName}</strong> 的历史数据...
            </span>
          `;
        }

        try {
          // 显式展示图表内部的加载动画（仅在真正发起历史请求时）
          if (historyChart && window.echarts) {
            historyChart.showLoading({
              text: '正在加载历史数据...',
              color: '#007AFF',
              textColor: '#86868b',
              maskColor: 'rgba(255, 255, 255, 0.8)'
            });
          }

          const data = await fetchJson(
            `/metrics/history?room_name=${encodeURIComponent(roomName)}&minutes=${HISTORY_MINUTES}`
          );

          // 防止竞态条件：如果用户已切换到其他房间，丢弃本次数据
          if (roomName !== selectedRoomName) {
            return;
          }

          if (!historyChart || !window.echarts) {
            return;
          }

          if (!data || data.length === 0) {
            historyChart.clear();
            if (summaryEl) {
              summaryEl.innerHTML = `
                <span>
                  <i class="fas fa-info-circle"></i>
                  当前暂未记录到 <strong>${roomName}</strong> 的历史指标数据。
                </span>
              `;
            }
            return;
          }

          // 按时间顺序准备数据
          const times = data.map((p) => p.created_at);
          const onlineSeries = data.map((p) => p.online_count);
          const likeSeries = data.map((p) => p.like_count);

          // 计算整体变化情况（首尾对比）
          const first = data[0];
          const last = data[data.length - 1];
          const deltaOnline = last.online_count - first.online_count;
          const deltaLike = last.like_count - first.like_count;

          const deltaOnlineText =
            deltaOnline === 0
              ? "基本持平"
              : `${deltaOnline > 0 ? "↑" : "↓"}${Math.abs(deltaOnline)} 人`;

          const deltaLikeText =
            deltaLike === 0
              ? "基本持平"
              : `${deltaLike > 0 ? "↑" : "↓"}${Math.abs(deltaLike)} 赞`;

          historyChart.setOption({
            tooltip: {
              trigger: "axis",
              backgroundColor: "rgba(255, 255, 255, 0.95)",
              borderColor: "rgba(0, 0, 0, 0.08)",
              borderWidth: 1,
              textStyle: { color: "#1d1d1f" },
              extraCssText: 'box-shadow: 0 4px 16px rgba(0,0,0,0.12); border-radius: 8px;'
            },
            legend: {
              data: ["在线人数", "本场点赞"],
              textStyle: { color: "#86868b", fontSize: 11 },
            },
            grid: {
              left: 50,
              right: 60,
              top: 50,
              bottom: 50,
            },
            xAxis: {
              type: "category",
              data: times.map((t) => formatTime(t)),
              axisLabel: {
                color: "#86868b",
                rotate: 30,
                fontSize: 10
              },
              axisLine: {
                lineStyle: { color: "rgba(0,0,0,0.08)" },
              },
            },
            yAxis: [
              {
                type: "value",
                name: "在线人数",
                nameTextStyle: { color: "#86868b", fontSize: 11 },
                axisLabel: {
                  color: "#86868b",
                  fontSize: 10,
                  formatter: function (value) {
                    return formatNumber(value);
                  },
                },
                splitLine: {
                  lineStyle: {
                    color: "rgba(0,0,0,0.04)",
                    type: "solid",
                  },
                },
                axisLine: { show: false },
              },
              {
                type: "value",
                name: "本场点赞",
                nameTextStyle: { color: "#86868b", fontSize: 11 },
                axisLabel: {
                  color: "#86868b",
                  fontSize: 10,
                  formatter: function (value) {
                    return formatNumber(value);
                  },
                },
                splitLine: {
                  show: false,
                },
                axisLine: { show: false },
              },
            ],
            series: [
              {
                name: "在线人数",
                type: "line",
                smooth: true,
                showSymbol: false,
                data: onlineSeries,
                lineStyle: {
                  width: 2.5,
                  color: "#007AFF",
                },
                itemStyle: {
                  color: "#007AFF",
                },
                areaStyle: {
                  color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: "rgba(0,122,255,0.15)" },
                    { offset: 1, color: "rgba(0,122,255,0.02)" }
                  ])
                },
              },
              {
                name: "本场点赞",
                type: "line",
                smooth: true,
                showSymbol: false,
                yAxisIndex: 1,
                data: likeSeries,
                lineStyle: {
                  width: 2.5,
                  color: "#FF9500",
                },
                itemStyle: {
                  color: "#FF9500",
                },
                areaStyle: {
                  color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: "rgba(255,149,0,0.15)" },
                    { offset: 1, color: "rgba(255,149,0,0.02)" }
                  ])
                },
              },
            ],
          });

          if (summaryEl) {
            const startText = formatTime(first.created_at);
            const endText = formatTime(last.created_at);
            summaryEl.innerHTML = `
              <span>
                <i class="fas fa-info-circle"></i>
                <strong>${roomName}</strong> 最近 ${HISTORY_MINUTES} 分钟内，
                在线人数整体变化：<strong>${deltaOnlineText}</strong>，
                点赞数整体变化：<strong>${deltaLikeText}</strong>。
              </span>
              <span>
                时间范围：<strong>${startText}</strong> ~ <strong>${endText}</strong>
              </span>
            `;
          }
        } catch (err) {
          console.error("加载历史数据失败:", err);
          if (summaryEl && !isAutoRefresh) {
            summaryEl.innerHTML = `
              <span>
                <i class="fas fa-exclamation-triangle" style="color:#f97316;"></i>
                历史数据加载失败，请稍后重试。
              </span>
            `;
          }
        } finally {
          // 无论成功或失败，都关闭图表内部加载动画，避免“圈圈”一直转
          if (historyChart && window.echarts) {
            historyChart.hideLoading();
          }
        }
      }

      function handleRoomRowClick(roomName, trElement) {
        if (!roomName) return;

        // 更新表格中的选中高亮
        const rows = document.querySelectorAll("#room-table-body tr");
        rows.forEach((row) => row.classList.remove("row-selected"));
        if (trElement) {
          trElement.classList.add("row-selected");
        }

        // 加载该直播间的历史趋势
        loadHistoryForRoom(roomName, false);
        // 重置历史数据轮询（立即开始新的周期）
        startHistoryPolling(roomName);
      }

      function renderCharts(overview) {
        // 如果 echarts 或图表实例尚未准备好，直接返回
        if (!window.echarts || !onlineChart || !likeChart) {
          return;
        }

        // 没有数据时，清空图表并隐藏“加载中”状态
        if (!overview.items || overview.items.length === 0) {
          onlineChart.hideLoading();
          likeChart.hideLoading();
          onlineChart.clear();
          likeChart.clear();
          return;
        }

        const liveItems = overview.items.filter((item) => item.latest_is_live);
        if (liveItems.length === 0) {
          onlineChart.hideLoading();
          likeChart.hideLoading();
          onlineChart.clear();
          likeChart.clear();
          return;
        }

        const names = liveItems.map((item) => item.room_name);
        const onlineData = liveItems.map((item) => item.latest_online_count);
        const likeData = liveItems.map((item) => item.latest_like_count);

        if (onlineChart) {
          onlineChart.hideLoading();
          onlineChart.setOption({
            tooltip: {
              trigger: "axis",
              backgroundColor: 'rgba(255, 255, 255, 0.95)',
              borderColor: 'rgba(0, 0, 0, 0.08)',
              borderWidth: 1,
              textStyle: { color: '#1d1d1f' },
              formatter: function(params) {
                const data = params[0];
                return `<div style="font-weight: 600; margin-bottom: 4px; color: #1d1d1f;">${data.name}</div>
                        <div style="color: #007AFF;">在线人数: ${data.value.toLocaleString()}</div>`;
              },
              extraCssText: 'box-shadow: 0 4px 16px rgba(0,0,0,0.12); border-radius: 8px;'
            },
            grid: {
              left: 50, right: 20, top: 40, bottom: 60,
              backgroundColor: 'transparent'
            },
            xAxis: {
              type: "category",
              data: names,
              axisLabel: {
                color: "#86868b",
                interval: 0,
                rotate: names.length > 4 ? 30 : 0,
                fontWeight: 500,
                fontSize: 11
              },
              axisLine: {
                lineStyle: { color: "rgba(0,0,0,0.08)", width: 1 }
              },
              axisTick: {
                lineStyle: { color: "rgba(0,0,0,0.08)" }
              }
            },
            yAxis: {
              type: "value",
              name: "在线人数",
              nameTextStyle: { color: "#86868b", fontWeight: 500, fontSize: 11 },
              axisLabel: {
                color: "#86868b",
                fontSize: 11,
                formatter: function(value) {
                  return formatNumber(value);
                }
              },
              splitLine: {
                lineStyle: {
                  color: "rgba(0,0,0,0.04)",
                  type: 'solid'
                }
              },
              axisLine: {
                show: false
              }
            },
            series: [
              {
                name: "在线人数",
                type: "bar",
                data: onlineData,
                itemStyle: {
                  color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: "#34C759" },
                    { offset: 1, color: "#30B350" }
                  ]),
                  borderRadius: [6, 6, 0, 0]
                },
                barWidth: '55%',
                emphasis: {
                  itemStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                      { offset: 0, color: "#40D964" },
                      { offset: 1, color: "#34C759" }
                    ])
                  }
                },
                animationDuration: 800,
                animationEasing: 'cubicOut'
              }
            ]
          }, true);
        }

        if (likeChart) {
          likeChart.hideLoading();
          likeChart.setOption({
            tooltip: {
              trigger: "axis",
              backgroundColor: 'rgba(255, 255, 255, 0.95)',
              borderColor: 'rgba(0, 0, 0, 0.08)',
              borderWidth: 1,
              textStyle: { color: '#1d1d1f' },
              formatter: function(params) {
                const data = params[0];
                return `<div style="font-weight: 600; margin-bottom: 4px; color: #1d1d1f;">${data.name}</div>
                        <div style="color: #FF9500;">本场点赞: ${data.value.toLocaleString()}</div>`;
              },
              extraCssText: 'box-shadow: 0 4px 16px rgba(0,0,0,0.12); border-radius: 8px;'
            },
            grid: {
              left: 50, right: 20, top: 40, bottom: 60,
              backgroundColor: 'transparent'
            },
            xAxis: {
              type: "category",
              data: names,
              axisLabel: {
                color: "#86868b",
                interval: 0,
                rotate: names.length > 4 ? 30 : 0,
                fontWeight: 500,
                fontSize: 11
              },
              axisLine: {
                lineStyle: { color: "rgba(0,0,0,0.08)", width: 1 }
              },
              axisTick: {
                lineStyle: { color: "rgba(0,0,0,0.08)" }
              }
            },
            yAxis: {
              type: "value",
              name: "本场点赞",
              nameTextStyle: { color: "#86868b", fontWeight: 500, fontSize: 11 },
              axisLabel: {
                color: "#86868b",
                fontSize: 11,
                formatter: function(value) {
                  return formatNumber(value);
                }
              },
              splitLine: {
                lineStyle: {
                  color: "rgba(0,0,0,0.04)",
                  type: 'solid'
                }
              },
              axisLine: {
                show: false
              }
            },
            series: [
              {
                name: "本场点赞",
                type: "line",
                smooth: true,
                showSymbol: true,
                symbolSize: 6,
                symbol: 'circle',
                data: likeData,
                lineStyle: {
                  width: 2.5,
                  color: "#FF9500"
                },
                itemStyle: {
                  color: "#FF9500",
                  borderColor: '#fff',
                  borderWidth: 2
                },
                areaStyle: {
                  color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: "rgba(255,149,0,0.2)" },
                    { offset: 1, color: "rgba(255,149,0,0.02)" }
                  ])
                },
                emphasis: {
                  itemStyle: {
                    color: '#FF9500',
                    borderColor: '#fff',
                    borderWidth: 3
                  }
                },
                animationDuration: 800,
                animationEasing: 'cubicOut'
              }
            ]
          }, true);
        }
      }

      function renderDanmu(danmuList) {
        const ul = document.getElementById("danmu-list");
        ul.innerHTML = "";

        // 更新弹幕总数和关键词统计区域
        const summaryEl = document.getElementById("danmu-summary");
        const totalEl = document.getElementById("danmu-total");
        const keywordsEl = document.getElementById("danmu-keywords");

        if (summaryEl && totalEl && keywordsEl) {
          const total = Array.isArray(danmuList) ? danmuList.length : 0;
          totalEl.textContent = total.toString();

          if (!danmuList || danmuList.length === 0) {
            keywordsEl.innerHTML = '<span class="keyword-tag muted">暂无弹幕，等待新的互动内容…</span>';
          } else {
            // 简单的关键词列表，可按需要调整 / 扩展
            const keywordList = ["优惠", "下单", "支持", "好喝", "活动", "价格", "送", "链接"];
            const counts = {};
            keywordList.forEach((k) => { counts[k] = 0; });

            danmuList.forEach((dm) => {
              const content = (dm.content || "").toString();
              keywordList.forEach((k) => {
                if (content.includes(k)) {
                  counts[k] += 1;
                }
              });
            });

            const hotKeywords = keywordList
              .filter((k) => counts[k] > 0)
              .sort((a, b) => counts[b] - counts[a])
              .slice(0, 5);

            if (hotKeywords.length === 0) {
              keywordsEl.innerHTML = '<span class="keyword-tag muted">暂无明显高频关键词</span>';
            } else {
              keywordsEl.innerHTML = hotKeywords.map((k) => `
                <span class="keyword-tag">
                  ${k}
                  <span class="keyword-count">${counts[k]}</span>
                </span>
              `).join("");
            }
          }
        }

        if (!danmuList || danmuList.length === 0) {
          const li = document.createElement("li");
          li.className = "danmu-item";
          li.innerHTML = '<i class="fas fa-info-circle"></i> 当前暂无弹幕数据。';
          ul.appendChild(li);
          return;
        }

        // 限制显示数量，避免页面过长
        const displayList = danmuList.slice(0, 20);

        displayList.forEach((dm, index) => {
          const li = document.createElement("li");
          li.className = "danmu-item";

          // 添加延迟动画效果，创建渐进式加载
          li.style.animationDelay = `${index * 0.1}s`;

          const timeSpan = document.createElement("span");
          timeSpan.className = "danmu-time";
          timeSpan.innerHTML = `<i class="fas fa-clock"></i> ${formatTime(dm.created_at)}`;
          li.appendChild(timeSpan);

          const nickSpan = document.createElement("span");
          nickSpan.className = "danmu-nickname";
          // 使用 textContent 避免 XSS 风险
          const nickIcon = document.createElement("i");
          nickIcon.className = "fas fa-user";
          nickSpan.appendChild(nickIcon);
          nickSpan.appendChild(document.createTextNode(" " + dm.sender_nickname + "："));
          li.appendChild(nickSpan);

          const contentSpan = document.createElement("span");
          contentSpan.textContent = dm.content;

          // 添加高亮效果，针对较长的弹幕或特殊关键词
          if (dm.content.length > 15 || dm.content.includes('666') || dm.content.includes('支持')) {
            contentSpan.style.fontWeight = '600';
            contentSpan.style.color = '#fbbf24';
          }

          li.appendChild(contentSpan);

          ul.appendChild(li);
        });

        // 如果有更多弹幕，添加提示
        if (danmuList.length > 20) {
          const li = document.createElement("li");
          li.className = "danmu-item";
          li.style.background = 'rgba(59, 130, 246, 0.1)';
          li.style.borderLeft = '3px solid #3b82f6';
          li.innerHTML = `
            <span class="danmu-time">更多</span>
            <span class="danmu-nickname">系统提示：</span>
            <span>还有 ${danmuList.length - 20} 条弹幕未显示，最近 10 分钟内共有 <strong>${danmuList.length}</strong> 条互动</span>
          `;
          ul.appendChild(li);
        }
      }

      // 启动或重置历史数据的自动刷新
      function startHistoryPolling(roomName) {
        if (historyTimer) {
          clearInterval(historyTimer);
          historyTimer = null;
        }
        if (autoRefreshEnabled && roomName) {
          historyTimer = setInterval(() => {
            loadHistoryForRoom(roomName, true);
          }, HISTORY_INTERVAL);
        }
      }

      // 仅刷新概览数据（高频）
      async function refreshOverview() {
        try {
          const [overview, danmu] = await Promise.all([
            fetchJson("/overview/live-rooms"),
            fetchJson("/danmu/jingjiu?limit=50"),
          ]);

          // 更新页面标题，显示实时状态
          const liveCount = overview.items ? overview.items.filter(item => item.latest_is_live).length : 0;
          document.title = `酒类直播监控雷达盘 (${liveCount}个直播中)`;

          renderRooms(overview);
          renderDanmu(danmu);
        } catch (err) {
          console.error("概览数据刷新失败:", err);

          // 显示错误提示
          const summaryBar = document.getElementById("summary-bar");
          if (summaryBar) {
            summaryBar.innerHTML = `
              <i class="fas fa-exclamation-triangle" style="color: #ef4444;"></i>
              数据更新失败，请检查网络连接或稍后重试
            `;
            summaryBar.style.background = 'rgba(239, 68, 68, 0.1)';
            summaryBar.style.borderColor = 'rgba(239, 68, 68, 0.3)';
          }
        }
      }

      // 手动触发单个直播间的状态重查，用于修正“误判为未开播”的情况
      async function manualRecheckRoom(roomName, buttonEl) {
        if (!roomName) return;

        const summaryBar = document.getElementById("summary-bar");
        const originalText = buttonEl ? buttonEl.textContent : "";

        if (buttonEl) {
          buttonEl.disabled = true;
          buttonEl.textContent = "检测中...";
        }

        if (summaryBar) {
          summaryBar.innerHTML = `
            <i class="fas fa-search"></i>
            正在重新检测 <strong>${roomName}</strong> 的直播状态，请稍候...
          `;
          summaryBar.style.background = "rgba(59, 130, 246, 0.08)";
          summaryBar.style.borderColor = "rgba(59, 130, 246, 0.4)";
        }

        try {
          const resp = await fetch(`/rooms/recheck?room_name=${encodeURIComponent(roomName)}`, {
            method: "POST",
          });
          if (!resp.ok) {
            throw new Error("重查请求失败: " + resp.status);
          }
          const data = await resp.json();

          // 在“重新检测”按钮旁边展示一个 3 秒自动消失的小气泡，直观说明本次重查结果
          if (buttonEl && buttonEl.parentElement) {
            const tooltip = document.createElement("span");
            const inserted = data && data.metric_inserted !== undefined ? data.metric_inserted : true;
            const liveText = data && data.is_live ? "直播中" : "未开播";

            tooltip.className = "recheck-tooltip " + (inserted ? "recheck-tooltip-ok" : "recheck-tooltip-warn");
            tooltip.innerHTML = inserted
              ? `<i class="fas fa-check"></i> 数据已更新(${liveText})`
              : `<i class="fas fa-exclamation-triangle"></i> 本次数据未写入，保持上次结果`;

            buttonEl.parentElement.appendChild(tooltip);
            setTimeout(() => {
              tooltip.remove();
            }, 3000);
          }

          if (summaryBar) {
            // 如果本次采集因为“数据不完整或疑似异常”未写入数据库，给出额外说明，方便你排查问题
            let extraNote = "";
            if (data && data.metric_inserted === false) {
              extraNote = `
                <span style="margin-left:8px;font-size:12px;color:#f97316;">
                  <i class="fas fa-exclamation-triangle"></i>
                  本次采集数据不完整或疑似异常，未写入数据库，当前展示的仍是最近一次有效记录。
                </span>
              `;
            }

            summaryBar.innerHTML = `
              <i class="fas fa-check-circle" style="color:#22c55e;"></i>
              已重新检测 <strong>${data.room_name}</strong>：当前状态
              <strong>${data.is_live ? "直播中" : "未开播"}</strong>，
              在线人数 <strong>${formatNumber(data.online_count)}</strong>，
              点赞 <strong>${formatNumber(data.like_count)}</strong>。
              ${extraNote}
            `;
            summaryBar.style.background = "rgba(34, 197, 94, 0.08)";
            summaryBar.style.borderColor = "rgba(34, 197, 94, 0.4)";
          }

          // 使用统一的全局刷新逻辑，确保排名、图表等全部使用最新数据
          await refreshOverview();
        } catch (err) {
          console.error("手动重查失败:", err);

          // 失败时，也在按钮旁给一个红色小气泡提示
          if (buttonEl && buttonEl.parentElement) {
            const tooltip = document.createElement("span");
            tooltip.className = "recheck-tooltip recheck-tooltip-error";
            tooltip.innerHTML = `<i class="fas fa-times-circle"></i> 重查失败`;
            buttonEl.parentElement.appendChild(tooltip);
            setTimeout(() => {
              tooltip.remove();
            }, 3000);
          }

          if (summaryBar) {
            summaryBar.innerHTML = `
              <i class="fas fa-exclamation-triangle" style="color:#f97316;"></i>
              手动重查失败，请检查服务端日志或稍后重试。
            `;
            summaryBar.style.background = "rgba(249, 115, 22, 0.08)";
            summaryBar.style.borderColor = "rgba(249, 115, 22, 0.4)";
          } else {
            alert("手动重查失败，请稍后重试。");
          }
        } finally {
          if (buttonEl) {
            buttonEl.disabled = false;
            buttonEl.textContent = originalText || "重新检测";
          }
        }
      }

      // 页面首次加载和每 5 秒自动刷新
      window.addEventListener("load", () => {
        // 初始化图表
        const onlineEl = document.getElementById("chart-online");
        const likeEl = document.getElementById("chart-like");
        const historyEl = document.getElementById("history-chart");

        if (onlineEl && window.echarts) {
          onlineChart = echarts.init(onlineEl);
          onlineChart.showLoading({
            text: '正在加载数据...',
            color: '#007AFF',
            textColor: '#86868b',
            maskColor: 'rgba(255, 255, 255, 0.8)'
          });
        }

        if (likeEl && window.echarts) {
          likeChart = echarts.init(likeEl);
          likeChart.showLoading({
            text: '正在加载数据...',
            color: '#FF9500',
            textColor: '#86868b',
            maskColor: 'rgba(255, 255, 255, 0.8)'
          });
        }

        if (historyEl && window.echarts) {
          historyChart = echarts.init(historyEl);
          // 历史趋势区域初始不展示加载动画，仅通过上方文案提示用户点击某个直播间
        }

        // 响应式处理
        window.addEventListener("resize", () => {
          if (onlineChart) onlineChart.resize();
          if (likeChart) likeChart.resize();
          if (historyChart) historyChart.resize();
        });

        // 初始数据加载
        refreshOverview();

        // 设置概览定时刷新 (5s)
        if (autoRefreshEnabled) {
          overviewTimer = setInterval(() => {
            refreshOverview();
          }, OVERVIEW_INTERVAL);
        }

        // 添加键盘快捷键支持
        document.addEventListener('keydown', (e) => {
          if (e.key === 'F5' || (e.ctrlKey && e.key === 'r')) {
            e.preventDefault();
            refreshOverview();
            if (selectedRoomName) loadHistoryForRoom(selectedRoomName, false);
          }
        });

        // 页面可见性变化时刷新数据（用户回到页面时）
        document.addEventListener('visibilitychange', () => {
          if (!document.hidden) {
            setTimeout(refreshOverview, 1000);
            if (selectedRoomName) loadHistoryForRoom(selectedRoomName, true);
          }
        });

        // 页面加载完成的视觉反馈
        document.body.style.opacity = '0';
        setTimeout(() => {
          document.body.style.transition = 'opacity 0.5s ease-out';
          document.body.style.opacity = '1';
        }, 50);
      });

      // 添加一些额外的交互效果 & 交互控制逻辑
      document.addEventListener('DOMContentLoaded', () => {
        // 为统计卡片添加点击效果
        const statCards = document.querySelectorAll('.stat-card');
        statCards.forEach(card => {
          card.addEventListener('click', () => {
            card.style.transform = 'scale(0.95)';
            setTimeout(() => {
              card.style.transform = '';
            }, 150);
          });
        });

        // 为图表添加鼠标悬停效果
        const chartBoxes = document.querySelectorAll('.chart-box');
        chartBoxes.forEach(box => {
          box.addEventListener('mouseenter', () => {
            box.style.zIndex = '10';
          });
          box.addEventListener('mouseleave', () => {
            box.style.zIndex = '';
          });
        });

        // 绑定筛选按钮事件（全部 / 仅直播中 / 仅其他直播间）
        const filterAllBtn = document.getElementById('filter-all');
        const filterLiveBtn = document.getElementById('filter-live');
        const filterOtherBtn = document.getElementById('filter-other');

        if (filterAllBtn && filterLiveBtn && filterOtherBtn) {
          filterAllBtn.addEventListener('click', () => {
            showOnlyLive = false;
            showOnlyOtherRooms = false;
            filterAllBtn.classList.add('active');
            filterLiveBtn.classList.remove('active');
            filterOtherBtn.classList.remove('active');
            if (lastOverview) {
              renderRooms(lastOverview);
            } else {
              refreshOverview();
            }
          });

          filterLiveBtn.addEventListener('click', () => {
            showOnlyLive = true;
            showOnlyOtherRooms = false;
            filterLiveBtn.classList.add('active');
            filterAllBtn.classList.remove('active');
            filterOtherBtn.classList.remove('active');
            if (lastOverview) {
              renderRooms(lastOverview);
            } else {
              refreshOverview();
            }
          });

          filterOtherBtn.addEventListener('click', () => {
            showOnlyLive = false;
            showOnlyOtherRooms = true;
            filterOtherBtn.classList.add('active');
            filterAllBtn.classList.remove('active');
            filterLiveBtn.classList.remove('active');
            if (lastOverview) {
              renderRooms(lastOverview);
            } else {
              refreshOverview();
            }
          });
        }

        // 绑定自动刷新控制
        const refreshToggleBtn = document.getElementById('refresh-toggle');
        const refreshNowBtn = document.getElementById('refresh-now');

        if (refreshToggleBtn) {
          refreshToggleBtn.addEventListener('click', () => {
            autoRefreshEnabled = !autoRefreshEnabled;

            if (autoRefreshEnabled) {
              refreshToggleBtn.classList.add('active');
              refreshToggleBtn.textContent = '每 5 秒自动刷新';
              // 恢复概览刷新
              if (!overviewTimer) {
                overviewTimer = setInterval(refreshOverview, OVERVIEW_INTERVAL);
              }
              // 恢复历史刷新
              if (selectedRoomName) {
                startHistoryPolling(selectedRoomName);
              }
            } else {
              refreshToggleBtn.classList.remove('active');
              refreshToggleBtn.textContent = '自动刷新已暂停';
              if (overviewTimer) {
                clearInterval(overviewTimer);
                overviewTimer = null;
              }
              if (historyTimer) {
                clearInterval(historyTimer);
                historyTimer = null;
              }
            }
          });
        }

        if (refreshNowBtn) {
          refreshNowBtn.addEventListener('click', () => {
            refreshOverview();
            if (selectedRoomName) loadHistoryForRoom(selectedRoomName, false);
          });
        }
      });
    </script>
  </body>
</html>
    """


@app.get("/health")
async def health_check():
    """健康检查接口，用于确认服务是否正常运行。"""
    return {"status": "ok"}


@app.get("/overview/live-rooms", response_model=schemas.LiveRoomOverviewList)
async def get_live_room_overview(
    db: AsyncSession = Depends(database.get_db),
):
    """
    获取所有直播间的概览信息。

    逻辑：
    1. 查询每个直播间最近的一条指标记录
    2. 统计最近一段时间（例如 10 分钟）内的弹幕数量
    3. 组装为前端需要的结构
    """
    latest_metrics = await crud.get_latest_metrics_for_all_rooms(db)

    items: List[schemas.LiveRoomOverview] = []
    for metric in latest_metrics:
        # 仅"中国劲酒"启用弹幕采集，其他直播间不需要额外的弹幕统计查询
        recent_danmu_count = 0
        if metric.room_name == "中国劲酒":
            recent_danmu_count = await crud.get_recent_danmu_count_for_room(
                db, room_name=metric.room_name, within_minutes=10
            )

        last_updated_at = (
            _as_utc(metric.created_at) if metric.created_at is not None else None
        )

        items.append(
            schemas.LiveRoomOverview(
                room_name=metric.room_name,
                room_url=metric.room_url,
                latest_online_count=metric.online_count,
                latest_like_count=metric.like_count,
                latest_is_live=metric.is_live,
                last_updated_at=last_updated_at,
                recent_danmu_count=recent_danmu_count,
            )
        )

    return schemas.LiveRoomOverviewList(items=items)


@app.get(
    "/danmu/jingjiu",
    response_model=List[schemas.DanmuMessageRead],
)
async def list_jingjiu_danmu(
    limit: int = 50,
    db: AsyncSession = Depends(database.get_db),
):
    """
    获取中国劲酒直播间最近的若干条弹幕。
    """
    danmu_list = await crud.list_danmu_for_room(
        db, room_name="中国劲酒", limit=limit
    )

    # 为了避免前端解析时间时出现 8 小时偏差，这里同样显式将时间标记为 UTC
    result: List[schemas.DanmuMessageRead] = []
    for dm in danmu_list:
        created_at = (
            _as_utc(dm.created_at) if dm.created_at is not None else None
        )
        result.append(
            schemas.DanmuMessageRead(
                id=dm.id,
                room_name=dm.room_name,
                sender_nickname=dm.sender_nickname,
                content=dm.content,
                metric_id=dm.metric_id,
                created_at=created_at,
            )
        )

    return result


@app.get(
    "/metrics/history",
    response_model=List[schemas.LiveRoomMetricHistoryPoint],
)
async def get_live_room_history(
    room_name: str,
    minutes: int = 60,
    db: AsyncSession = Depends(database.get_db),
):
    """
    获取指定直播间最近一段时间的历史指标，用于前端画折线图。

    说明：
    - room_name：直播间名称（例如“中国劲酒”）
    - minutes：时间窗口，单位分钟（默认 60，最小 1，最大 1440）
    """
    # 简单做一下参数边界保护，避免一次性扫太多历史数据
    if minutes < 1:
        minutes = 60
    if minutes > 24 * 60:
        minutes = 24 * 60

    since = datetime.utcnow() - timedelta(minutes=minutes)

    records = await crud.list_metrics_for_room_since(
        db, room_name=room_name, since=since
    )

    result: List[schemas.LiveRoomMetricHistoryPoint] = []
    for r in records:
        created_at = (
            _as_utc(r.created_at) if r.created_at is not None else None
        )
        result.append(
            schemas.LiveRoomMetricHistoryPoint(
                room_name=r.room_name,
                room_url=r.room_url,
                online_count=r.online_count,
                like_count=r.like_count,
                is_live=r.is_live,
                created_at=created_at,
            )
        )

    return result


@app.post("/rooms/recheck", response_model=schemas.RoomRecheckResponse)
async def recheck_room(
    room_name: str,
    db: AsyncSession = Depends(database.get_db),
):
    """
    手动触发单个直播间状态重查。

    使用场景：
    - 当后台逻辑认为“未开播”但你怀疑判断有误时，
      可以在前端点击按钮调用本接口，强制重新抓取一次该房间的实时数据。
    """
    # 在模拟数据模式下不支持真实重查，避免产生误导性的“假结果”
    if settings.use_fake_data_only:
        raise HTTPException(
            status_code=400,
            detail="当前运行在模拟数据模式(use_fake_data_only=True)，无法执行真实重查。",
        )

    # 校验房间是否在当前配置列表中
    room_url = crawler_tasks.LIVE_ROOMS.get(room_name)
    if not room_url:
        raise HTTPException(status_code=404, detail=f"未配置直播间: {room_name}")

    # 仅中国劲酒开启弹幕采集，其他直播间只采集指标
    enable_danmu = room_name == "中国劲酒"

    client = DouyinLiveClient(persistent_single_room=enable_danmu)
    try:
        await client.init()
        metric = await crawler_tasks._crawl_room_once(
            db=db,
            client=client,
            room_name=room_name,
            room_url=room_url,
            enable_danmu=enable_danmu,
        )
    except Exception as exc:  # noqa: BLE001
        # 不把 Playwright 等底层异常细节直接暴露给前端，仅提示用户查看服务端日志
        raise HTTPException(
            status_code=500,
            detail="重查直播间失败，请查看服务器日志。",
        ) from exc
    finally:
        await client.close()

    # 统一从数据库中读取“最新一条指标记录”，避免直接依赖内部实现细节
    latest_metric = await crud.get_latest_metric_for_room(db, room_name)
    if latest_metric is None:
        raise HTTPException(
            status_code=500,
            detail="重查完成，但仍未找到任何指标记录，请检查爬虫任务。",
        )

    created_at = (
        _as_utc(latest_metric.created_at)
        if latest_metric.created_at is not None
        else None
    )

    return schemas.RoomRecheckResponse(
        room_name=latest_metric.room_name,
        room_url=latest_metric.room_url,
        online_count=latest_metric.online_count,
        like_count=latest_metric.like_count,
        is_live=latest_metric.is_live,
        created_at=created_at,
        metric_inserted=metric is not None
        and latest_metric.id == metric.id,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
