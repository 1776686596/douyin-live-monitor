"""
配置模块：集中管理项目中的配置项。

实际部署时建议：
1. 使用环境变量管理敏感信息（数据库账号等）
2. 配合 .env 文件或容器环境注入
"""

# 注意：在 Pydantic v2 中，BaseSettings 被移动到了单独的 pydantic-settings 包中
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """全局配置对象，后续可根据需要扩展。"""

    # MySQL 连接配置
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "200303"
    mysql_db: str = "jj_douyin"

    # 爬虫相关配置（单位：秒）
    # 旧的统一间隔配置，保留以兼容早期代码（目前以更细粒度配置为主）
    crawl_interval_seconds: int = 10

    # 中国劲酒专用抓取间隔（秒），适当更高频以捕获弹幕与状态变化
    jingjiu_interval_seconds: int = 5

    # 其他酒类直播间抓取间隔（秒），可相对降低频率
    other_rooms_interval_seconds: int = 15
    # 其他直播间并发抓取上限（建议 2~3；设为 1 等价于串行，便于回滚）
    other_rooms_concurrency: int = 2

    # 是否在启动时自动启动爬虫后台任务
    enable_background_crawler: bool = True

    # 是否只使用模拟数据（不真实请求抖音），用于本地演示或网络受限场景
    # True：后台任务不会通过 Playwright 访问抖音，而是生成模拟数据写入数据库
    # False：后台任务会尝试真实访问抖音直播间（需要网络环境支持）
    use_fake_data_only: bool = False


    # Playwright / 浏览器相关配置
    # 在本地开发阶段可以设置为 False 方便调试，服务器上建议保持 True 减少资源占用
    playwright_headless: bool = True

    # 页面加载超时时间（毫秒），用于控制单次打开直播间的等待时间
    playwright_navigation_timeout_ms: int = 30000
    # 页面就绪等待策略
    # - True：等待"关键元素出现"后继续（更快；最坏情况仍等到超时）
    # - False：回退到固定等待 5 秒（旧逻辑，便于快速止损/回滚）
    enable_room_page_smart_wait: bool = True
    # 智能等待的最长时长（毫秒）
    room_page_smart_wait_timeout_ms: int = 5000
    # 认为"页面关键模块已就绪"的候选选择器（逗号分隔；命中任一即可提前结束等待）
    room_page_smart_wait_selectors: str = (
        'div[data-e2e="live-room-audience"],'
        'div:has-text("本场点赞"),'
        "div.webcast-chatroom___list"
    )

    # 单次抓取弹幕时最多解析的条数（预留给弹幕抓取逻辑使用）
    danmu_max_items_per_fetch: int = 30

    # 日志与调试相关配置
    # - enable_crawler_debug_log: 控制是否在终端打印详细的异常和调试信息
    #   默认关闭，避免刷屏影响性能；需要排查问题时可以临时打开
    # - enable_crawler_metric_log: 控制是否在每次成功写入指标时打印一行简要信息
    #   默认开启，方便你观察各直播间当前抓取到的数据
    enable_crawler_debug_log: bool = False
    enable_crawler_metric_log: bool = True

    # 是否在进入直播间后模拟部分“人工操作”（移动/点击/滚动等）
    # 设计目的：
    # 1. 触发页面内部的懒加载和前端逻辑，确保弹幕、人数等模块正常渲染
    # 2. 避免浏览器长期完全静止，有助于提高采集的稳定性和数据可靠性
    enable_human_like_actions: bool = True

    # 直播间状态抓取重试配置
    # 当首次未能从页面中解析出在线人数和点赞数（两者都为 0）时，
    # 会在同一页面上额外等待一段时间并重试若干次，避免误判“未开播”。
    # 注意：重试会延长单次采集时间，但可以显著降低错误数据。
    room_info_retry_times: int = 2  # 额外重试次数（总共最多采集 1 + room_info_retry_times 次）
    room_info_retry_interval_ms: int = 3000  # 每次重试前额外等待的时间（毫秒）
    # 开播判定策略（多信号 + 三态）
    # - True：启用 LIVE/OFFLINE/UNKNOWN 三态（UNKNOWN 不等于未开播）
    # - False：回退到旧的二值逻辑（在线>0 或 点赞>0 即视为直播中）
    enable_three_state_live_detection: bool = True
    # 识别"未开播/已结束"页面的关键词（逗号分隔，命中任一视为 OFFLINE 信号）
    # 注意：避免使用过宽的词如"回放"，可能在直播中页面也出现
    room_offline_text_keywords: str = "直播已结束,已结束直播,直播结束,主播已离开"
    # 识别"直播中"的聊天活跃信号（用于在线/点赞解析失败时兜底）
    room_live_chat_message_selector: str = (
        "div.webcast-chatroom___list "
        "span.webcast-chatroom___content-with-emoji-text"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
