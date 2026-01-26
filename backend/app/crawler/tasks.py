"""
爬虫任务调度。

这里定义后台任务，用于周期性地：
1. 轮询各个直播间（劲酒/茅台/五粮液等），抓取在线人数与点赞数
2. 针对中国劲酒房间，抓取弹幕数据
3. 将数据写入数据库

第一版实现只做“假数据写入”，验证后端 + 数据库 + API 整体流程；
之后再替换为调用 DouyinLiveClient 的真实爬虫逻辑。
"""

import asyncio
import random
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from .. import crud, schemas
from .douyin_client import DouyinLiveClient, LiveRoomInfo, LiveState


# 初始直播间列表（可以后续改为从配置或数据库读取）
LIVE_ROOMS: Dict[str, str] = {
    "中国劲酒": "https://live.douyin.com/720433616435",
    "茅台": "https://live.douyin.com/250926880704",
    "五粮液": "https://live.douyin.com/884334047259",
    "泸州老窖": "https://live.douyin.com/7629359417",
    "剑南春": "https://live.douyin.com/986058521905",
    "汾酒": "https://live.douyin.com/865319483235",
}

# 用于模拟数据的基础值（仅在 use_fake_data_only=True 时生效）
FAKE_ROOM_BASE_METRICS: Dict[str, Dict[str, int]] = {
    "中国劲酒": {"online": 2000, "like": 80000},
    "茅台": {"online": 5000, "like": 200000},
    "五粮液": {"online": 3500, "like": 150000},
    "泸州老窖": {"online": 1800, "like": 60000},
    "剑南春": {"online": 1600, "like": 55000},
    "汾酒": {"online": 1400, "like": 50000},
}


async def run_crawler_loop(db_factory) -> None:
    """
    后台循环任务入口。

    思路：
    - 为“中国劲酒”和“其他直播间”分别启动一个独立的循环任务
    - 每个循环使用自己的 DouyinLiveClient 实例，互不干扰
    - 劲酒循环可以设置更高频率，优先保障弹幕和状态的采集
    """
    # 如果配置为“只使用模拟数据”，则直接进入单循环的模拟模式
    if settings.use_fake_data_only:
        await _run_single_loop_with_fake_data(db_factory)
        return

    # 真实采集模式：为劲酒和其他直播间分别创建客户端与循环。
    # 注意：如果 Playwright 或浏览器环境未准备好，init() 会抛出异常，
    # 此时整个后台任务会报错，从而提醒你修复真实采集链路。
    # 不再自动降级为模拟数据，以保证“监控数据一定是真实来源”。
    # 劲酒客户端启用“单房间持久页面”模式，方便持续抓取弹幕与指标
    client_jingjiu = DouyinLiveClient(persistent_single_room=True)
    client_other = DouyinLiveClient()

    await client_jingjiu.init()
    await client_other.init()

    async def jingjiu_loop() -> None:
        try:
            while True:
                try:
                    async with db_factory() as db:
                        await _crawl_jingjiu_once(db, client_jingjiu)
                except Exception as exc:  # noqa: BLE001
                    # 循环级别的异常通常意味着严重问题，这里始终打印，方便及时发现
                    print(f"[Crawler] 劲酒循环异常: {exc}")

                await asyncio.sleep(settings.jingjiu_interval_seconds)
        finally:
            await client_jingjiu.close()

    async def other_rooms_loop() -> None:
        try:
            while True:
                try:
                    async with db_factory() as db:
                        await _crawl_other_rooms_once(db, client_other)
                except Exception as exc:  # noqa: BLE001
                    print(f"[Crawler] 其他直播间循环异常: {exc}")

                await asyncio.sleep(settings.other_rooms_interval_seconds)
        finally:
            await client_other.close()

    await asyncio.gather(jingjiu_loop(), other_rooms_loop())


async def _run_single_loop_with_fake_data(db_factory) -> None:
    """
    仅在 use_fake_data_only=True 时使用的单循环逻辑。

    为了保持代码清晰，真实采集与模拟数据的逻辑拆开处理。
    """
    while True:
        try:
            async with db_factory() as db:
                await _crawl_all_rooms_with_fake_data(db)
        except Exception as exc:  # noqa: BLE001
            print(f"[Crawler] 模拟数据循环异常: {exc}")

        await asyncio.sleep(settings.crawl_interval_seconds)


async def _crawl_all_rooms_with_fake_data(db: AsyncSession) -> None:
    """
    使用模拟数据写入所有直播间指标，仅用于本地演示或网络受限场景。
    """
    for room_name, room_url in LIVE_ROOMS.items():
        base = FAKE_ROOM_BASE_METRICS.get(
            room_name, {"online": 100, "like": 1000}
        )
        online_count = max(0, base["online"] + random.randint(-50, 50))
        like_count = max(0, base["like"] + random.randint(-2000, 2000))
        is_live = True

        metric_in = schemas.LiveRoomMetricCreate(
            room_name=room_name,
            room_url=room_url,
            online_count=online_count,
            like_count=like_count,
            is_live=is_live,
        )
        await crud.create_live_room_metric(db, metric_in)


async def _crawl_jingjiu_once(
    db: AsyncSession,
    client: DouyinLiveClient,
) -> None:
    """单轮采集中国劲酒直播间数据（指标 + 弹幕）。"""
    room_name = "中国劲酒"
    room_url = LIVE_ROOMS[room_name]
    await _crawl_room_once(
        db=db,
        client=client,
        room_name=room_name,
        room_url=room_url,
        enable_danmu=True,
    )


async def _crawl_other_rooms_once(
    db: AsyncSession,
    client: DouyinLiveClient,
) -> None:
    """单轮采集其他酒类直播间数据（仅指标）。"""
    # 并发抓取：先并发获取数据，再串行落库（AsyncSession 不支持并发复用）
    rooms: List[Tuple[str, str]] = [
        (room_name, room_url)
        for room_name, room_url in LIVE_ROOMS.items()
        if room_name != "中国劲酒"
    ]
    if not rooms:
        return

    concurrency = max(1, int(settings.other_rooms_concurrency or 1))
    sem = asyncio.Semaphore(concurrency)

    async def _fetch_one(name: str, url: str) -> Tuple[str, str, LiveRoomInfo]:
        async with sem:
            info = await client.fetch_room_info(room_name=name, room_url=url)
            return name, url, info

    results = await asyncio.gather(
        *[asyncio.create_task(_fetch_one(name, url)) for name, url in rooms],
        return_exceptions=True,
    )

    for res in results:
        if isinstance(res, Exception):
            print(f"[Crawler] 其他直播间并发抓取异常: {res}")
            continue

        room_name, room_url, room_info = res
        await _crawl_room_once(
            db=db,
            client=client,
            room_name=room_name,
            room_url=room_url,
            enable_danmu=False,
            prefetched_room_info=room_info,
        )


async def _crawl_room_once(
    db: AsyncSession,
    client: Optional[DouyinLiveClient],
    room_name: str,
    room_url: str,
    enable_danmu: bool,
    prefetched_room_info: Optional[LiveRoomInfo] = None,
) -> None:
    """
    单个直播间的一次采集逻辑。

    当前支持两种模式：
    1. use_fake_data_only = True：由 _crawl_all_rooms_with_fake_data 负责
    2. use_fake_data_only = False：使用 DouyinLiveClient.fetch_room_info 访问抖音获取真实数据

    参数：
        enable_danmu: 是否为该直播间启用弹幕采集（目前仅中国劲酒为 True）
        prefetched_room_info: 预抓取的直播间信息（用于"并发抓取 + 串行落库"）
    """
    live_state = LiveState.UNKNOWN
    if client is not None:
        # 真实爬虫模式：调用 DouyinLiveClient 获取直播间实时数据
        room_info = prefetched_room_info or await client.fetch_room_info(
            room_name=room_name, room_url=room_url
        )
        online_count = room_info.online_count
        like_count = room_info.like_count
        live_state = room_info.live_state
    else:
        # 模拟数据模式：根据预设基础值生成一组略有波动的假数据
        base = FAKE_ROOM_BASE_METRICS.get(
            room_name, {"online": 100, "like": 1000}
        )
        online_count = max(0, base["online"] + random.randint(-50, 50))
        like_count = max(0, base["like"] + random.randint(-2000, 2000))
        # 模拟为正在直播
        live_state = LiveState.LIVE

    is_live = live_state == LiveState.LIVE

    # 决定是否写入数据库：
    # 1. 未开播：只在“状态变化为未开播”时写入一条记录，避免大量重复“未开播”行
    # 2. 直播中但指标不完整（人数和点赞都为 0）：认为抓取失败，不写入记录，下次循环重试
    should_insert_metric = True
    latest_metric = await crud.get_latest_metric_for_room(db, room_name)

    if client is not None:
        # 仅在真实爬虫模式下启用更严格的"数据合理性"校验，
        # 避免 DOM 解析异常导致的明显错误值覆盖历史正常数据。
        if live_state == LiveState.UNKNOWN:
            # 无法确认开播状态：不写入数据库，保持最近一次有效记录
            if settings.enable_crawler_debug_log:
                print(
                    f"[Crawler] {room_name} 本次抓取状态=UNKNOWN，"
                    "为避免误写数据，本次不写入数据库，将在下次循环重试。"
                )
            should_insert_metric = False
        elif live_state == LiveState.OFFLINE:
            # OFFLINE：写入"未开播"只需表达状态，人数/点赞统一归零
            online_count = 0
            like_count = 0
            if latest_metric is not None:
                if latest_metric.is_live:
                    # 上一条仍是"直播中"，且时间间隔较短时，
                    # 直接从有数据跌到 0/0 很可能是解析失败，先暂不写入"未开播"记录。
                    last_ts = latest_metric.created_at
                    if isinstance(last_ts, datetime):
                        delta = datetime.utcnow() - last_ts
                        # 这里给一个宽限时间窗口：例如 2 分钟内的瞬时 0/0 先视为异常
                        if delta.total_seconds() < 120:
                            if settings.enable_crawler_debug_log:
                                print(
                                    f"[Crawler] {room_name} 最近一次仍为直播中，"
                                    "本次采集到 OFFLINE，疑似解析失败，本次不写入未开播记录。"
                                )
                            should_insert_metric = False
                else:
                    # 上一次已经是未开播，则不重复写入大量"未开播"行
                    should_insert_metric = False
        else:
            # 直播中：如果人数和点赞都为 0，视为抓取异常，不写入记录，下次重试
            if online_count <= 0 and like_count <= 0:
                if settings.enable_crawler_debug_log:
                    print(
                        f"[Crawler] {room_name} 直播中但未成功获取人数/点赞，"
                        "本次不写入数据库，将在下次循环重试。"
                    )
                should_insert_metric = False

            # 直播中但在线人数为 0、点赞 > 0：常见于解析到"历史/静态点赞"但实际未拿到在线
            elif online_count <= 0 and like_count > 0:
                if settings.enable_crawler_debug_log:
                    print(
                        f"[Crawler] {room_name} 本次在线=0但点赞>0，疑似解析异常，"
                        "本次不写入数据库，将在下次循环重试。"
                    )
                should_insert_metric = False

            # 直播中但点赞数为 0（例如"茅台 145 人在线，点赞=0"），
            # 在正常直播情况下几乎不会出现，通常意味着本次抓取 DOM 解析异常。
            elif online_count > 0 and like_count <= 0:
                if settings.enable_crawler_debug_log:
                    print(
                        f"[Crawler] {room_name} 直播中但本次未成功获取点赞数，"
                        "本次不写入数据库，将在下次循环重试。"
                    )
                should_insert_metric = False

    metric = None
    if should_insert_metric:
        metric_in = schemas.LiveRoomMetricCreate(
            room_name=room_name,
            room_url=room_url,
            online_count=online_count,
            like_count=like_count,
            is_live=is_live,
        )
        metric = await crud.create_live_room_metric(db, metric_in)

        # 为方便你观察每次成功写入数据库的抓取结果，这里输出一行简要日志。
        # 日志粒度为“成功落库的快照”，数量远小于调试信息，对性能影响很小。
        if settings.enable_crawler_metric_log:
            ts_str = (
                metric.created_at.strftime("%H:%M:%S")
                if isinstance(metric.created_at, datetime)
                else ""
            )
            status_str = "直播中" if metric.is_live else "未开播"
            print(
                f"[Metric] {ts_str} | {metric.room_name} | 状态={status_str} | "
                f"在线={metric.online_count} | 点赞={metric.like_count}"
            )

    # 弹幕抓取逻辑：
    # 仅当：
    # - 启用了弹幕采集（enable_danmu=True）
    # - 当前直播间正在直播
    # - 本轮已成功写入对应的直播指标（metric 不为 None）
    # - 且处于真实爬虫模式（client 不为 None）
    if (
        enable_danmu
        and client is not None
        and metric is not None
        and is_live
    ):
        danmu_items = await client.fetch_danmu_snapshot(
            room_name=room_name,
            room_url=room_url,
        )

        for item in danmu_items:
            danmu_in = schemas.DanmuMessageCreate(
                room_name=item.room_name,
                sender_nickname=item.sender_nickname,
                content=item.content,
                metric_id=metric.id,
            )
            await crud.create_danmu_message(db, danmu_in)

    # 返回本轮插入的指标记录（若因数据校验未写入，则为 None），便于 API 等调用方了解结果
    return metric
