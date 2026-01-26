"""
抖音直播间客户端封装（基于 Playwright）。

核心职责：
1. 启动无头 Chromium 浏览器
2. 打开抖音直播间页面
3. 解析 DOM，获取在线人数、点赞数等数据

说明：
- 抖音页面结构有可能调整，本实现以你提供的 DOM 信息为基础，
  尽量使用 data-e2e 或文本选择器来提高稳定性。
- 如果后续发现选择器失效，只需要在本文件里微调解析逻辑即可。
"""

import asyncio
import random
import re
from dataclasses import dataclass
from enum import Enum
from typing import AsyncIterator, Dict, List, Optional, Set, Tuple

from playwright.async_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    Playwright,
    async_playwright,
)

from ..config import settings


class LiveState(str, Enum):
    """
    直播状态三态枚举：
    - LIVE：确认直播中
    - OFFLINE：确认未开播/已结束
    - UNKNOWN：无法确认（解析失败/页面异常/信号冲突）
    """

    LIVE = "LIVE"
    OFFLINE = "OFFLINE"
    UNKNOWN = "UNKNOWN"


@dataclass
class LiveRoomInfo:
    """单个直播间的基本信息与实时数据。"""

    room_name: str
    room_url: str
    live_state: LiveState
    online_count: int
    like_count: int

    @property
    def is_live(self) -> bool:
        """
        为兼容旧代码保留的布尔字段语义：
        - 仅当 live_state == LIVE 时返回 True
        - UNKNOWN 返回 False（调用方应优先使用 live_state 做决策）
        """
        return self.live_state == LiveState.LIVE


@dataclass
class DanmuItem:
    """弹幕数据结构。"""

    room_name: str
    sender_nickname: str
    content: str


class DouyinLiveClient:
    """
    抖音直播间爬虫客户端。

    建议使用方式（当前版本）：
    1. 在应用启动时创建实例并调用 `init()`
    2. 在后台任务中反复调用 `fetch_room_info()` 获取实时指标
    3. 在应用关闭时调用 `close()` 释放资源
    """

    def __init__(self, persistent_single_room: bool = False) -> None:
        # Playwright 相关内部状态
        self._initialized: bool = False
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

        # 配置项（来自 config.Settings）
        self._headless: bool = settings.playwright_headless
        self._navigation_timeout_ms: int = settings.playwright_navigation_timeout_ms
        self._danmu_max_items: int = settings.danmu_max_items_per_fetch
        self._enable_human_like_actions: bool = settings.enable_human_like_actions
        self._enable_room_page_smart_wait: bool = settings.enable_room_page_smart_wait
        self._room_page_smart_wait_timeout_ms: int = (
            settings.room_page_smart_wait_timeout_ms
        )
        self._room_page_smart_wait_selectors: List[str] = self._split_csv(
            settings.room_page_smart_wait_selectors
        )
        self._enable_three_state_live_detection: bool = (
            settings.enable_three_state_live_detection
        )
        self._offline_text_keywords: List[str] = self._split_csv(
            settings.room_offline_text_keywords
        )
        self._live_chat_message_selector: str = (
            settings.room_live_chat_message_selector
        )

        # 弹幕去重缓存：按房间名记录最近见过的弹幕 key（room|nickname|content）
        self._danmu_seen: Dict[str, Set[str]] = {}

        # 是否启用“单房间持久页面”模式：
        # - True：客户端主要服务于单个直播间（如中国劲酒），内部会复用同一个 Page，不在每次调用后关闭页面，
        #   适合需要持续抓取弹幕和指标的场景。
        # - False：每次调用都会创建并关闭一个新的 Page，适合其他直播间的低频抓取。
        self._persistent_single_room: bool = persistent_single_room
        self._persistent_page: Optional[Page] = None
        self._persistent_room_url: Optional[str] = None

    async def _simulate_human_actions(self, page: Page) -> None:
        """
        简单模拟若干“人工操作”，帮助触发页面内部脚本与懒加载。

        设计思路：
        1. 随机等待 + 鼠标缓慢移动，避免页面长时间完全静止
        2. 轻微点击页面中间区域，常见于激活页面或关闭蒙层
        3. 适度滚动，帮助弹幕列表等区域完成懒加载

        注意：该方法不依赖具体业务按钮，尽量保持“无副作用”的通用行为。
        """
        try:
            # 1. 初始随机等待，避免动作过于机械
            await page.wait_for_timeout(random.randint(800, 2500))

            viewport = page.viewport_size
            if viewport:
                width = viewport["width"]
                height = viewport["height"]
            else:
                # 兜底视口尺寸
                width, height = 1280, 720

            # 2. 在页面中间区域随机选一点，模拟人把鼠标移到内容区域
            x = random.randint(int(width * 0.3), int(width * 0.7))
            y = random.randint(int(height * 0.3), int(height * 0.7))

            await page.mouse.move(x, y, steps=random.randint(5, 20))
            await page.mouse.click(x, y, delay=random.randint(50, 200))

            # 3. 尝试让弹幕区域滚动一下（如果存在的话）
            try:
                chat_locator = page.locator("div.webcast-chatroom___list")
                if await chat_locator.count() > 0:
                    await chat_locator.first.scroll_into_view_if_needed()
                    await page.wait_for_timeout(random.randint(500, 1500))
            except Exception:
                # 局部滚动失败不影响整体流程
                pass

            # 4. 整体页面轻微向下滚动，帮助其他区域加载
            await page.mouse.wheel(0, random.randint(200, 800))
        except Exception as exc:  # noqa: BLE001
            # 为了健壮性，任何模拟动作失败都不应影响主流程
            if settings.enable_crawler_debug_log:
                print(f"[DouyinLiveClient] 模拟人工操作失败: {exc}")

    async def _simulate_danmu_scroll_pattern(self, page: Page) -> None:
        """
        针对“单房间弹幕抓取模式”的滚动节奏模拟。

        目标：
        1. 在长时间采集过程中，模拟用户多次轻微滚动与阅读停顿
        2. 尽量不改变页面业务状态，仅在弹幕区域内做小幅移动

        设计：
        - 只在 persistent_single_room=True 且启用了拟人行为时调用
        - 循环若干次：滚动少量距离 + 短暂停顿
        """
        # 仅在单房间持久页面模式下启用，避免影响其他直播间
        if not self._persistent_single_room:
            return

        # 这里选取较小的循环次数与间隔，兼顾“拟人感”和整体抓取频率
        cycles = 3
        base_interval_ms = 900

        try:
            for _ in range(cycles):
                chat_locator = page.locator("div.webcast-chatroom___list")
                if await chat_locator.count() > 0:
                    # 确保弹幕区域在视口内
                    await chat_locator.first.scroll_into_view_if_needed()

                    # 在弹幕区域附近做一次轻微的上下滚动
                    direction = random.choice([-1, 1])
                    delta = random.randint(150, 320) * direction
                    await page.mouse.wheel(0, delta)
                else:
                    # 找不到弹幕列表时，退回到整体页面的轻微滚动
                    await page.mouse.wheel(0, random.randint(150, 320))

                # 每次滚动后稍作停顿，模拟用户阅读弹幕
                jitter = random.randint(-250, 250)
                await page.wait_for_timeout(max(200, base_interval_ms + jitter))
        except Exception as exc:  # noqa: BLE001
            if settings.enable_crawler_debug_log:
                print(f"[DouyinLiveClient] 弹幕滚动节奏模拟失败: {exc}")

    async def init(self) -> None:
        """
        初始化浏览器实例。

        实际流程：
        - playwright = await async_playwright().start()
        - browser = await playwright.chromium.launch(headless=True, ...)
        """
        if self._initialized:
            return

        self._playwright = await async_playwright().start()
        # 选择 Chromium，抖音对 Chromium 系浏览器支持较好
        self._browser = await self._playwright.chromium.launch(
            headless=self._headless,
        )

        # 创建“无痕窗口”（独立上下文），类似浏览器的隐身模式
        # 同时设置一个常见的桌面浏览器 UA 和中文环境，尽量模拟真实用户
        self._context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
        )
        self._initialized = True

    async def close(self) -> None:
        """关闭浏览器实例并清理资源。"""
        if self._persistent_page is not None:
            try:
                await self._persistent_page.close()
            except Exception:
                pass
            self._persistent_page = None
            self._persistent_room_url = None
        if self._context is not None:
            await self._context.close()
            self._context = None

        if self._browser is not None:
            await self._browser.close()
            self._browser = None

        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """确保浏览器已经初始化。"""
        if not self._initialized:
            await self.init()

    @staticmethod
    def _split_csv(raw: str) -> List[str]:
        """将逗号分隔字符串解析为列表。"""
        if not raw:
            return []
        return [part.strip() for part in raw.split(",") if part.strip()]

    async def _smart_wait_room_ready(self, page: Page) -> None:
        """
        用"关键元素就绪"替代固定 5 秒等待。

        设计目标：
        - 页面很快就绪时显著提速（提前结束等待）
        - 页面较慢时不牺牲稳定性（最坏情况等到 timeout）
        - 可通过 settings.enable_room_page_smart_wait 一键回滚到旧逻辑
        """
        if not self._enable_room_page_smart_wait:
            await page.wait_for_timeout(5000)
            return

        timeout_ms = int(self._room_page_smart_wait_timeout_ms or 0)
        if timeout_ms <= 0:
            return

        selectors = [s for s in self._room_page_smart_wait_selectors if s]
        if not selectors:
            await page.wait_for_timeout(timeout_ms)
            return

        # 尝试等待 DOMContentLoaded
        try:
            await page.wait_for_load_state(
                "domcontentloaded", timeout=min(timeout_ms, 3000)
            )
        except Exception:
            pass

        tasks = [
            asyncio.create_task(
                page.wait_for_selector(
                    selector, state="attached", timeout=timeout_ms
                )
            )
            for selector in selectors
        ]

        try:
            await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_COMPLETED,
                timeout=timeout_ms / 1000,
            )
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _detect_offline_by_text(self, page: Page) -> bool:
        """通过页面文案判断"未开播/已结束"。"""
        if not self._offline_text_keywords:
            return False

        for kw in self._offline_text_keywords:
            try:
                if await page.locator(f"text={kw}").count() > 0:
                    return True
            except Exception:
                continue

        return False

    async def _detect_live_by_chat_activity(self, page: Page) -> bool:
        """通过"聊天区是否出现弹幕内容节点"判断直播中（兜底信号）。"""
        selector = (self._live_chat_message_selector or "").strip()
        if not selector:
            return False

        try:
            return await page.locator(selector).count() > 0
        except Exception:
            return False

    @staticmethod
    def _decide_live_state(
        *,
        offline_hit: bool,
        online_count: int,
        like_count: int,
        chat_active: bool,
    ) -> LiveState:
        """
        多信号三态判定：
        - LIVE：在线人数 > 0 或 聊天活跃
        - OFFLINE：命中离线文案，且无 LIVE 信号
        - UNKNOWN：解析失败或信号冲突
        """
        live_by_online = online_count > 0
        live_by_chat = chat_active

        if offline_hit and (live_by_online or live_by_chat):
            return LiveState.UNKNOWN
        if live_by_online or live_by_chat:
            return LiveState.LIVE
        if offline_hit:
            return LiveState.OFFLINE

        return LiveState.UNKNOWN

    async def _extract_room_metrics(
        self,
        page: Page,
        room_name: str,
        room_url: str,
    ) -> Tuple[int, int]:
        """
        从当前直播间页面中解析在线人数和点赞数。

        说明：
        - 不负责判断是否开播，仅返回两个原始数值
        - 调用方可以根据多次采集结果自行决定“是否开播”
        """
        online_count = 0
        like_count = 0

        # 1. 在线人数：优先使用相对稳定的 data-e2e；严格路径仅作为最后兜底
        try:
            audience_locator = page.locator('div[data-e2e="live-room-audience"]')
            if await audience_locator.count() > 0:
                text = (await audience_locator.first.inner_text()).strip()
                online_count = self._parse_number_from_text(text)
            else:
                # 精确 CSS 选择器（来自你在 request.md 中的 JS 路径）
                audience_selector_strict = (
                    "#chatroom > div.c9Poqbe4.unset-border > "
                    "div.LyAdeVIF.sBRqUw32 > div.sDE_n_gz.dmp0TnCf > "
                    "div.ClV317pr"
                )
                audience_elem = await page.query_selector(audience_selector_strict)
                if audience_elem is not None:
                    text = (await audience_elem.inner_text()).strip()
                    online_count = self._parse_number_from_text(text)
        except Exception as exc:  # noqa: BLE001
            # 在线人数解析失败通常意味着选择器失效或页面结构变化，
            # 这里仅在打开调试开关时打印详细错误，避免在正常运行时刷屏。
            if settings.enable_crawler_debug_log:
                print(
                    f"[DouyinLiveClient] 获取在线人数失败: {room_name} {room_url} - {exc}"
                )

        # 2. 点赞数：优先使用"本场点赞"文本；严格路径仅作为最后兜底
        try:
            like_locator = page.locator('div:has-text("本场点赞")')
            if await like_locator.count() > 0:
                text = (await like_locator.first.inner_text()).strip()
                like_count = self._parse_number_from_text(text)
            else:
                # 精确 CSS 选择器（来自你在 request.md 中的 JS 路径）
                like_selector_strict = (
                    "#room_info_bar > div.F4gIvJUc > "
                    "div.AZr5KmrG.__leftContainer.yu4z0zVP > "
                    "div.CsUBJdAJ.v1wQQUfA > div > div > div"
                )
                like_elem = await page.query_selector(like_selector_strict)
                if like_elem is not None:
                    text = (await like_elem.inner_text()).strip()
                    like_count = self._parse_number_from_text(text)
        except Exception as exc:  # noqa: BLE001
            if settings.enable_crawler_debug_log:
                print(
                    f"[DouyinLiveClient] 获取点赞数失败: {room_name} {room_url} - {exc}"
                )

        return online_count, like_count

    @staticmethod
    def _parse_number_from_text(text: str) -> int:
        """
        从包含中文描述的文本中解析数字。

        兼容以下形式：
        - "966本场点赞"
        - "1.2w本场点赞"
        - "1.2万"
        - "26"（纯数字）
        """
        raw = text.replace(",", "").strip()

        # 匹配数字 + 可选单位（w/W/万）
        m = re.search(r"([\d.]+)\s*([wW万]?)", raw)
        if not m:
            # 兜底：把所有数字拼起来
            digits = re.findall(r"\d+", raw)
            if not digits:
                return 0
            return int("".join(digits))

        value_str, unit = m.groups()
        try:
            value = float(value_str)
        except ValueError:
            return 0

        if unit in ("w", "W", "万"):
            value *= 10000

        return int(value)

    async def _open_room_page(self, room_url: str) -> Optional[Page]:
        """
        打开直播间页面并返回 Page 对象。

        若打开失败则返回 None。
        """
        await self._ensure_initialized()

        assert self._context is not None  # 仅为类型检查服务

        # 若启用单房间持久页面模式，复用同一个 Page
        if self._persistent_single_room:
            # 如果没有有效的持久页面，或当前页面已关闭，则创建新的页面
            if self._persistent_page is None or self._persistent_page.is_closed():
                self._persistent_page = await self._context.new_page()
                self._persistent_page.set_default_timeout(
                    self._navigation_timeout_ms
                )
                self._persistent_room_url = None

            page = self._persistent_page
        else:
            # 非持久模式：每次新建页面
            page = await self._context.new_page()
            page.set_default_timeout(self._navigation_timeout_ms)

        try:
            # 只有当当前页面的 URL 与目标不同，或尚未导航过时，才执行跳转
            if not self._persistent_single_room or self._persistent_room_url != room_url:
                await page.goto(
                    room_url,
                    wait_until="commit",
                    timeout=self._navigation_timeout_ms,
                )
                # 用"关键元素就绪"替代固定 5s 盲等：更快且不降低稳定性
                await self._smart_wait_room_ready(page)

                # 可选：在进入直播间后模拟一些轻量级的"人工操作"，
                # 主要用于触发懒加载/前端逻辑，提升数据采集的稳定性。
                if self._enable_human_like_actions:
                    await self._simulate_human_actions(page)

                if self._persistent_single_room:
                    self._persistent_room_url = room_url
        except Exception as exc:  # noqa: BLE001
            # 打开页面失败是较严重的问题，调试时建议保留日志；
            # 为避免频繁刷屏，这里同样受 enable_crawler_debug_log 控制。
            if settings.enable_crawler_debug_log:
                print(f"[DouyinLiveClient] 打开直播间失败: {room_url} - {exc}")

            if not self._persistent_single_room:
                # 非持久模式出错时直接关闭本次页面
                await page.close()
            else:
                # 持久模式出错时重置持久页面，等待下次重新创建
                self._persistent_page = None
                self._persistent_room_url = None

            return None

        return page

    async def fetch_room_info(
        self,
        room_name: str,
        room_url: str,
    ) -> LiveRoomInfo:
        """
        获取单个直播间当前的在线人数、点赞数和开播状态。

        实现思路：
        1. 打开直播间页面
        2. 使用 data-e2e / 文本选择器定位在线人数与点赞数
        3. 支持 LIVE/OFFLINE/UNKNOWN 三态
           - UNKNOWN 不等价于未开播（避免 DOM 解析失败导致误判）
        """
        page = await self._open_room_page(room_url)
        if page is None:
            # 打不开页面：不做"未开播"武断判断，返回 UNKNOWN 以避免误写数据
            return LiveRoomInfo(
                room_name=room_name,
                room_url=room_url,
                live_state=LiveState.UNKNOWN,
                online_count=0,
                like_count=0,
            )

        # 第一次尝试从页面中解析指标
        online_count, like_count = await self._extract_room_metrics(
            page=page,
            room_name=room_name,
            room_url=room_url,
        )

        offline_hit = False
        if self._enable_three_state_live_detection:
            # 优先识别"已结束/未开播"页面，避免无意义的重试等待
            offline_hit = await self._detect_offline_by_text(page)

        # 为了尽量避免"在线人数/点赞数为 0 的异常数据"，
        # 在任意一个指标为 0 时，会在同一页面上额外等待一段时间并重试若干次。
        best_online = online_count
        best_like = like_count

        if (
            (online_count <= 0 or like_count <= 0)
            and settings.room_info_retry_times > 0
            and not offline_hit
        ):
            for _ in range(settings.room_info_retry_times):
                try:
                    # 等待页面进一步加载/渲染
                    await page.wait_for_timeout(
                        settings.room_info_retry_interval_ms
                    )
                except Exception:
                    # 如果页面已关闭或等待失败，直接结束重试
                    break

                retry_online, retry_like = await self._extract_room_metrics(
                    page=page,
                    room_name=room_name,
                    room_url=room_url,
                )

                # 取多次尝试中的"最好结果"：只要出现更大的有效值就更新
                if retry_online > best_online:
                    best_online = retry_online
                if retry_like > best_like:
                    best_like = retry_like

                # 若已经同时拿到"在线人数 > 0 且 点赞数 > 0"，认为数据足够可靠，可以提前结束重试
                if best_online > 0 and best_like > 0:
                    break

        online_count = best_online
        like_count = best_like

        # 三态判定
        if self._enable_three_state_live_detection:
            chat_active = False
            # 在线解析失败/矛盾值时，使用"聊天活跃"做兜底（避免漏检在播）
            if not offline_hit and online_count <= 0:
                chat_active = await self._detect_live_by_chat_activity(page)

            live_state = self._decide_live_state(
                offline_hit=offline_hit,
                online_count=online_count,
                like_count=like_count,
                chat_active=chat_active,
            )
        else:
            # 回滚逻辑：沿用旧的二值判定（在线>0 或 点赞>0 视为直播中）
            live_state = (
                LiveState.LIVE
                if (online_count > 0 or like_count > 0)
                else LiveState.OFFLINE
            )

        # 对于"持久单房间"模式（例如中国劲酒专用客户端），不关闭页面，
        # 以便后续弹幕抓取与下一次指标采集复用同一个 Page，减少反复打开成本。
        if not self._persistent_single_room:
            await page.close()

        return LiveRoomInfo(
            room_name=room_name,
            room_url=room_url,
            live_state=live_state,
            online_count=online_count,
            like_count=like_count,
        )

    async def stream_danmu(
        self,
        room_name: str,
        room_url: str,
    ) -> AsyncIterator[List[DanmuItem]]:
        """
        持续流式返回弹幕列表的迭代器（预留接口）。

        当前版本先保留接口形状，方便未来扩展真实的弹幕监听逻辑。
        实际项目中可以：
        1. 打开直播间页面
        2. 通过 `div.webcast-chatroom___list` 定位弹幕列表
        3. 使用 `div:has(span.v8LY0gZF)` 等选择器获取每条弹幕
        4. 维护“已见弹幕集合”，只 yield 新增的记录
        """
        if False:  # 仅用于占位，避免语法错误
            yield []  # pragma: no cover

    async def fetch_danmu_snapshot(
        self,
        room_name: str,
        room_url: str,
    ) -> List[DanmuItem]:
        """
        抓取当前页面上最新一批弹幕（快照）。

        说明：
        - 不做持续监听，而是在单次调用中抓取当前可见的若干条弹幕
        - 通过 `_danmu_seen` 去重，避免在多次循环中重复写入同一条弹幕

        选择器策略基于你提供的 DOM 结构：
        - 每条弹幕容器同时包含：
          - span.v8LY0gZF（昵称，例如“小*****：”）
          - span.webcast-chatroom___content-with-emoji-text（弹幕内容）
        """
        page = await self._open_room_page(room_url)
        if page is None:
            return []

        # 针对“中国劲酒”这类单房间弹幕采集场景，在每次抓取前执行一轮
        # “多次轻微滚动 + 阅读停顿”的交互节奏，有助于长时间运行时保持弹幕区域活跃。
        if self._enable_human_like_actions and self._persistent_single_room:
            await self._simulate_danmu_scroll_pattern(page)

        danmu_items: List[DanmuItem] = []
        seen_set = self._danmu_seen.setdefault(room_name, set())

        try:
            # 定位弹幕容器：在 webcast-chatroom___list 下，同时拥有昵称和内容的元素
            container_locator: Locator = page.locator(
                "div.webcast-chatroom___list "
                "div:has(span.v8LY0gZF)"
                ":has(span.webcast-chatroom___content-with-emoji-text)"
            )

            total = await container_locator.count()
            if total == 0:
                return []

            start_index = max(0, total - self._danmu_max_items)

            for idx in range(start_index, total):
                container = container_locator.nth(idx)
                try:
                    nick_el = container.locator("span.v8LY0gZF").first
                    content_el = container.locator(
                        "span.webcast-chatroom___content-with-emoji-text"
                    ).first

                    nickname_raw = (await nick_el.inner_text()).strip()
                    # 去掉昵称后面的冒号与空格
                    sender_nickname = nickname_raw.rstrip("：: ").strip()
                    content = (await content_el.inner_text()).strip()

                    if not sender_nickname or not content:
                        continue

                    key = f"{room_name}|{sender_nickname}|{content}"
                    if key in seen_set:
                        continue

                    seen_set.add(key)
                    danmu_items.append(
                        DanmuItem(
                            room_name=room_name,
                            sender_nickname=sender_nickname,
                            content=content,
                        )
                    )
                except Exception:
                    # 单条弹幕解析失败不影响整体，可忽略
                    continue

            # 简单控制缓存大小，避免无限增长
            max_cache_size = self._danmu_max_items * 10
            if len(seen_set) > max_cache_size:
                # 策略很简单：如果缓存过大，直接清空，让后续重新采集
                self._danmu_seen[room_name] = set()

            return danmu_items
        finally:
            # 持久单房间模式下保持页面打开；否则按调用方的期望关闭页面
            if not self._persistent_single_room and page is not None:
                await page.close()
