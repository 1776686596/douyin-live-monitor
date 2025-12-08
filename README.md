# 🎯 抖音酒类直播间监控系统

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.100+-green.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/Playwright-1.40+-purple.svg" alt="Playwright">
  <img src="https://img.shields.io/badge/MySQL-8.0+-orange.svg" alt="MySQL">
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg" alt="Platform">
</p>

一个基于 **Playwright** 和 **FastAPI** 的抖音直播间数据监控系统，可实时采集多个酒类品牌直播间的在线人数、点赞数和弹幕数据。

## ✨ 功能特性

- 🔴 **实时监控**：自动采集多个酒类直播间的在线人数和点赞数
- 💬 **弹幕采集**：针对中国劲酒直播间进行弹幕内容抓取
- 📊 **数据可视化**：内置 Web 界面展示实时排行榜和趋势图表
- 🗄️ **数据持久化**：所有数据存储到 MySQL 数据库，支持历史分析
- 🤖 **智能反检测**：模拟人工操作行为，提高采集稳定性
- 🔄 **自动重试**：内置重试机制，确保数据采集的可靠性

## 📸 界面预览

启动服务后访问 `http://localhost:8001` 即可看到监控面板：

- 📈 各直播间人气排行榜
- 📉 历史趋势对比图表
- 💬 中国劲酒实时弹幕列表
- 📊 核心数据统计卡片

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                      前端展示层                              │
│              (内嵌 HTML + ECharts 图表)                      │
├─────────────────────────────────────────────────────────────┤
│                      API 接口层                              │
│                    (FastAPI REST)                           │
├─────────────────────────────────────────────────────────────┤
│                      业务逻辑层                              │
│              (CRUD 操作 + 数据处理)                          │
├─────────────────────────────────────────────────────────────┤
│                      数据采集层                              │
│            (Playwright 浏览器自动化)                         │
├─────────────────────────────────────────────────────────────┤
│                      数据存储层                              │
│              (MySQL + SQLAlchemy ORM)                       │
└─────────────────────────────────────────────────────────────┘
```

## 📁 项目结构

```
jj/
├── requirements.txt            # Python 依赖
├── README.md                   # 项目说明
├── backend/                    # 后端代码
│   └── app/
│       ├── __init__.py
│       ├── main.py            # FastAPI 应用入口
│       ├── config.py          # 配置管理
│       ├── database.py        # 数据库连接
│       ├── models.py          # 数据表模型
│       ├── schemas.py         # Pydantic 模型
│       ├── crud.py            # 数据库操作
│       └── crawler/           # 爬虫模块
│           ├── __init__.py
│           ├── douyin_client.py  # 抖音直播间客户端
│           └── tasks.py          # 后台采集任务
├── database/                   # 数据库相关
│   └── mysql/
│       └── init.sql/          # 初始化脚本
└── docs/                       # 文档
    └── design.md              # 设计说明
```

## 🚀 快速开始

### 环境要求

- **Python**: 3.8 或更高版本
- **MySQL**: 8.0 或更高版本
- **操作系统**: Windows / Linux / macOS

---

## 🪟 Windows 安装指南

### 1. 安装 Python

从 [Python 官网](https://www.python.org/downloads/) 下载并安装 Python 3.8+，安装时勾选 **"Add Python to PATH"**。

验证安装：
```powershell
python --version
pip --version
```

### 2. 安装 MySQL

**方式一：使用 MySQL Installer（推荐）**
1. 下载 [MySQL Installer](https://dev.mysql.com/downloads/installer/)
2. 选择 "Developer Default" 或 "Server only"
3. 设置 root 密码（记住这个密码）

**方式二：使用 XAMPP**
1. 下载 [XAMPP](https://www.apachefriends.org/)
2. 安装后启动 MySQL 服务

### 3. 创建数据库

打开 MySQL 命令行或使用 MySQL Workbench：
```sql
CREATE DATABASE jj_douyin CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 4. 克隆项目并安装依赖

```powershell
# 克隆项目（或下载 ZIP 解压）
git clone <repository-url>
cd jj

# 创建虚拟环境（在项目根目录）
python -m venv venv
.\venv\Scripts\activate

# 安装 Python 依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium
```

### 5. 配置数据库连接

编辑 `backend/app/config.py`，修改数据库配置：
```python
mysql_host: str = "127.0.0.1"
mysql_port: int = 3306
mysql_user: str = "root"
mysql_password: str = "你的MySQL密码"
mysql_db: str = "jj_douyin"
```

或者在项目根目录创建 `.env` 文件：
```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=你的MySQL密码
MYSQL_DB=jj_douyin
```

### 6. 启动服务

```powershell
# 在项目根目录下启动服务（确保虚拟环境已激活）
uvicorn backend.app.main:app --reload --port 8001
```

### 7. 访问服务

打开浏览器访问：http://localhost:8001

---

## 🐧 Linux 安装指南

### Ubuntu / Debian

```bash
# 1. 更新系统
sudo apt update && sudo apt upgrade -y

# 2. 安装 Python 和 pip
sudo apt install python3 python3-pip python3-venv -y

# 3. 安装 MySQL
sudo apt install mysql-server -y
sudo systemctl start mysql
sudo systemctl enable mysql

# 4. 配置 MySQL
sudo mysql_secure_installation
sudo mysql -u root -p
```

```sql
-- 在 MySQL 中执行
CREATE DATABASE jj_douyin CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'jj_user'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON jj_douyin.* TO 'jj_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

```bash
# 5. 安装 Playwright 系统依赖
sudo apt install libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 -y

# 6. 克隆项目
git clone <repository-url>
cd jj

# 7. 创建虚拟环境（在项目根目录）
python3 -m venv venv
source venv/bin/activate

# 8. 安装依赖
pip install -r requirements.txt
playwright install chromium

# 9. 配置数据库（编辑 backend/app/config.py 或在项目根目录创建 .env 文件）

# 10. 启动服务（在项目根目录）
uvicorn backend.app.main:app --reload --port 8001
```

### CentOS / RHEL

```bash
# 1. 安装 Python 3.8+
sudo yum install python38 python38-pip -y

# 2. 安装 MySQL 8.0
sudo yum install mysql-server -y
sudo systemctl start mysqld
sudo systemctl enable mysqld

# 3. 获取临时密码并配置
sudo grep 'temporary password' /var/log/mysqld.log
sudo mysql_secure_installation

# 后续步骤与 Ubuntu 相同
```

---

## 🍎 macOS 安装指南

### 使用 Homebrew

```bash
# 1. 安装 Homebrew（如果没有）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. 安装 Python
brew install python@3.11

# 3. 安装 MySQL
brew install mysql
brew services start mysql

# 4. 配置 MySQL
mysql_secure_installation
mysql -u root -p
```

```sql
-- 在 MySQL 中执行
CREATE DATABASE jj_douyin CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
EXIT;
```

```bash
# 5. 克隆项目
git clone <repository-url>
cd jj

# 6. 创建虚拟环境（在项目根目录）
python3 -m venv venv
source venv/bin/activate

# 7. 安装依赖
pip install -r requirements.txt
playwright install chromium

# 8. 启动服务（在项目根目录）
uvicorn backend.app.main:app --reload --port 8001
```

---

## 🐳 Docker 部署（推荐）

### 使用 Docker Compose

创建 `docker-compose.yml`（在项目根目录）：

```yaml
version: '3.8'

services:
  mysql:
    image: mysql:8.0
    container_name: jj-mysql
    environment:
      MYSQL_ROOT_PASSWORD: your_password
      MYSQL_DATABASE: jj_douyin
      MYSQL_CHARACTER_SET_SERVER: utf8mb4
      MYSQL_COLLATION_SERVER: utf8mb4_unicode_ci
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: jj-backend
    environment:
      MYSQL_HOST: mysql
      MYSQL_PORT: 3306
      MYSQL_USER: root
      MYSQL_PASSWORD: your_password
      MYSQL_DB: jj_douyin
    ports:
      - "8001:8001"
    depends_on:
      mysql:
        condition: service_healthy

volumes:
  mysql_data:
```

创建 `Dockerfile`（在项目根目录）：

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 安装 Playwright 浏览器
RUN playwright install chromium

# 复制应用代码
COPY backend/ ./backend/

# 启动命令
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

启动服务：
```bash
docker-compose up -d
```

---

## ⚙️ 配置说明

### 主要配置项 (`backend/app/config.py`)

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `mysql_host` | `127.0.0.1` | MySQL 主机地址 |
| `mysql_port` | `3306` | MySQL 端口 |
| `mysql_user` | `root` | MySQL 用户名 |
| `mysql_password` | - | MySQL 密码 |
| `mysql_db` | `jj_douyin` | 数据库名称 |
| `enable_background_crawler` | `True` | 是否启动后台爬虫 |
| `use_fake_data_only` | `False` | 是否使用模拟数据 |
| `playwright_headless` | `True` | 是否无头模式运行浏览器 |
| `jingjiu_interval_seconds` | `5` | 中国劲酒采集间隔（秒） |
| `other_rooms_interval_seconds` | `15` | 其他直播间采集间隔（秒） |

### 环境变量

支持通过 `.env` 文件或环境变量覆盖配置：

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DB=jj_douyin
ENABLE_BACKGROUND_CRAWLER=true
USE_FAKE_DATA_ONLY=false
PLAYWRIGHT_HEADLESS=true
```

---

## 📡 API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 监控面板首页 |
| `/health` | GET | 健康检查 |
| `/overview/live-rooms` | GET | 获取所有直播间概览 |
| `/danmu/jingjiu` | GET | 获取中国劲酒弹幕列表 |
| `/metrics/history` | GET | 获取直播间历史数据 |
| `/rooms/recheck` | POST | 手动重新检测直播间状态 |

---

## 🔧 常见问题

### Q: Playwright 安装失败？

**Windows:**
```powershell
# 以管理员身份运行
playwright install chromium --with-deps
```

**Linux:**
```bash
# 安装系统依赖
sudo playwright install-deps chromium
playwright install chromium
```

### Q: MySQL 连接失败？

1. 确认 MySQL 服务已启动
2. 检查用户名和密码是否正确
3. 确认数据库 `jj_douyin` 已创建
4. 检查防火墙是否允许 3306 端口

### Q: 采集不到数据？

1. 检查网络是否能访问抖音
2. 尝试设置 `playwright_headless: false` 查看浏览器行为
3. 查看终端日志输出
4. 设置 `enable_crawler_debug_log: true` 获取详细日志

### Q: 如何只使用模拟数据测试？

在 `backend/app/config.py` 中设置：
```python
use_fake_data_only: bool = True
```

---

## 📝 开发说明

### 本地开发

```bash
# 进入项目目录
cd jj

# 激活虚拟环境
source venv/bin/activate  # Linux/macOS
# 或
.\venv\Scripts\activate   # Windows

# 安装开发依赖
pip install -r requirements.txt

# 启动开发服务器（支持热重载，在项目根目录执行）
uvicorn backend.app.main:app --reload --port 8001
```

### 代码结构

- `backend/app/main.py`: FastAPI 应用入口和路由定义
- `backend/app/config.py`: 配置管理（支持环境变量）
- `backend/app/models.py`: SQLAlchemy 数据模型
- `backend/app/schemas.py`: Pydantic 请求/响应模型
- `backend/app/crud.py`: 数据库 CRUD 操作
- `backend/app/crawler/douyin_client.py`: Playwright 浏览器自动化
- `backend/app/crawler/tasks.py`: 后台采集任务调度

---

## 📄 许可证

MIT License

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

## ⚠️ 免责声明

本项目仅供学习和研究使用，请遵守抖音平台的使用条款和相关法律法规。使用本项目采集数据时，请确保：

1. 不用于商业用途
2. 不对平台造成过大压力
3. 遵守数据隐私相关法规