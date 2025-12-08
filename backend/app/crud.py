"""
数据库 CRUD 封装。

这里提供对直播间指标和弹幕的基础读写接口，
方便在爬虫任务和 API 中复用，避免到处写 SQL。
"""

from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from . import models, schemas


async def create_live_room_metric(
    db: AsyncSession, metric_in: schemas.LiveRoomMetricCreate
) -> models.LiveRoomMetric:
    """创建一条直播间指标记录。"""
    live_status = "直播中" if metric_in.is_live else "未开播"

    db_obj = models.LiveRoomMetric(
        room_name=metric_in.room_name,
        room_url=metric_in.room_url,
        online_count=metric_in.online_count,
        like_count=metric_in.like_count,
        is_live=metric_in.is_live,
        live_status=live_status,
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def get_latest_metric_for_room(
    db: AsyncSession,
    room_name: str,
) -> Optional[models.LiveRoomMetric]:
    """
    获取某个直播间最新的一条指标记录。

    用于在写入新数据前判断：
    - 上一次是否已经记录为“未开播”（避免重复写入大量未开播记录）
    - 上一次是否为“直播中”，方便做状态变化分析
    """
    stmt = (
        select(models.LiveRoomMetric)
        .where(models.LiveRoomMetric.room_name == room_name)
        .order_by(desc(models.LiveRoomMetric.created_at))
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def create_danmu_message(
    db: AsyncSession, danmu_in: schemas.DanmuMessageCreate
) -> models.DanmuMessage:
    """创建一条弹幕记录。"""
    db_obj = models.DanmuMessage(
        room_name=danmu_in.room_name,
        sender_nickname=danmu_in.sender_nickname,
        content=danmu_in.content,
        metric_id=danmu_in.metric_id,
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def get_latest_metrics_for_all_rooms(
    db: AsyncSession,
) -> List[models.LiveRoomMetric]:
    """
    获取每个直播间最新的一条指标记录。

    简化实现：按 room_name 分组，取 created_at 最大的记录。
    """
    subquery = (
        select(
            models.LiveRoomMetric.room_name,
            func.max(models.LiveRoomMetric.created_at).label("max_created_at"),
        )
        .group_by(models.LiveRoomMetric.room_name)
        .subquery()
    )

    stmt = (
        select(models.LiveRoomMetric)
        .join(
            subquery,
            (models.LiveRoomMetric.room_name == subquery.c.room_name)
            & (models.LiveRoomMetric.created_at == subquery.c.max_created_at),
        )
        .order_by(models.LiveRoomMetric.room_name)
    )

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_recent_danmu_count_for_room(
    db: AsyncSession,
    room_name: str,
    within_minutes: int = 10,
) -> int:
    """
    获取某个直播间最近一段时间内的弹幕数量。
    """
    since_time = datetime.utcnow() - timedelta(minutes=within_minutes)
    stmt = (
        select(func.count(models.DanmuMessage.id))
        .where(models.DanmuMessage.room_name == room_name)
        .where(models.DanmuMessage.created_at >= since_time)
    )
    result = await db.execute(stmt)
    return int(result.scalar() or 0)


async def list_danmu_for_room(
    db: AsyncSession,
    room_name: str,
    limit: int = 50,
) -> List[models.DanmuMessage]:
    """
    获取某个直播间最近若干条弹幕记录（用于前端展示）。
    """
    stmt = (
        select(models.DanmuMessage)
        .where(models.DanmuMessage.room_name == room_name)
        .order_by(desc(models.DanmuMessage.created_at))
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_metrics_for_room_since(
    db: AsyncSession,
    room_name: str,
    since: datetime,
) -> List[models.LiveRoomMetric]:
    """
    获取某个直播间自指定时间点以来的所有指标快照。

    用途：
    - 为前端提供“最近 N 分钟/小时”的折线图数据
    - 只按时间正序返回，便于前端直接映射到 x 轴
    """
    stmt = (
        select(models.LiveRoomMetric)
        .where(models.LiveRoomMetric.room_name == room_name)
        .where(models.LiveRoomMetric.created_at >= since)
        .order_by(models.LiveRoomMetric.created_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
