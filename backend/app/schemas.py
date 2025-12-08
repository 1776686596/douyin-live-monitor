"""
Pydantic 数据模型。

用于定义 API 输入/输出的数据结构，与数据库模型解耦。
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


class LiveRoomMetricBase(BaseModel):
    """直播间指标基础字段，供创建/读取共用。"""

    room_name: str
    room_url: str
    online_count: int
    like_count: int
    is_live: bool


class LiveRoomMetricCreate(LiveRoomMetricBase):
    """创建直播间指标时使用的模型。"""

    pass


class LiveRoomMetricRead(LiveRoomMetricBase):
    """接口返回用的直播间指标模型。"""

    id: int
    created_at: datetime

    class Config:
        orm_mode = True


class DanmuMessageBase(BaseModel):
    """弹幕基础字段。"""

    room_name: str
    sender_nickname: str
    content: str


class DanmuMessageCreate(DanmuMessageBase):
    metric_id: Optional[int] = None


class DanmuMessageRead(DanmuMessageBase):
    id: int
    metric_id: Optional[int] = None
    created_at: datetime

    class Config:
        orm_mode = True


class LiveRoomOverview(BaseModel):
    """
    前端首页使用的“直播间概览”结构：
    - 最近一次快照的在线人数、点赞数
    - 最近一段时间的弹幕数量
    """

    room_name: str
    room_url: str
    latest_online_count: int
    latest_like_count: int
    latest_is_live: bool
    last_updated_at: Optional[datetime]
    recent_danmu_count: int


class LiveRoomOverviewList(BaseModel):
    """直播间概览列表，用于前端排名展示。"""

    items: List[LiveRoomOverview]


class LiveRoomMetricHistoryPoint(BaseModel):
    """
    单个直播间历史指标点，用于前端绘制趋势图。

    说明：
    - 只返回核心数值与时间戳，避免把整行 ORM 模型直接暴露给前端
    - room_url 一并返回，方便前端在趋势区域提供跳转链接（可选）
    """

    room_name: str
    room_url: str
    online_count: int
    like_count: int
    is_live: bool
    created_at: datetime

    class Config:
        orm_mode = True


class RoomRecheckResponse(BaseModel):
    """
    手动触发单个直播间重新检测后的结果。

    用途：
    - 当前端点击“重新检测”按钮时，返回该直播间最新的核心指标与状态
    """

    room_name: str
    room_url: str
    online_count: int
    like_count: int
    is_live: bool
    created_at: Optional[datetime]
    metric_inserted: bool
