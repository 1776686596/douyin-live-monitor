"""
数据库模型定义。

当前包含两个核心表：
1. LiveRoomMetric：直播间实时指标（在线人数、点赞数、是否开播等）
2. DanmuMessage：中国劲酒直播间弹幕数据
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    BigInteger,
    Text,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from .database import Base


class LiveRoomMetric(Base):
    """直播间指标表，用于存储每个时间点的直播数据快照。"""

    __tablename__ = "live_room_metric"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # 直播间名称，例如“中国劲酒”“茅台”
    room_name = Column(String(64), nullable=False, index=True)

    # 对应的抖音直播间链接
    room_url = Column(String(255), nullable=False)

    # 在线人数（如无法获取，记为 0）
    online_count = Column(Integer, nullable=False, default=0)

    # 点赞数（如无法获取，记为 0）
    like_count = Column(BigInteger, nullable=False, default=0)

    # 是否正在开播；如果检测到未开播，这里为 False
    is_live = Column(Boolean, nullable=False, default=True)

    # 文本形式的开播状态，便于在数据库中直观查看
    # 建议约定：
    # - "直播中"：正在开播
    # - "未开播"：当前未开播或无法获取数据
    live_status = Column(String(16), nullable=False, default="未开播")

    # 记录创建时间（爬取时间点）
    created_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, index=True
    )

    # 关联的弹幕（仅中国劲酒直播间会有数据）
    danmu_messages = relationship(
        "DanmuMessage",
        back_populates="room",
        lazy="selectin",
    )


class DanmuMessage(Base):
    """弹幕表，仅记录中国劲酒直播间的弹幕。"""

    __tablename__ = "danmu_message"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # 所属直播间名称（冗余字段，方便直接查询）
    room_name = Column(String(64), nullable=False, index=True)

    # 发送人昵称（示例：小*****）
    sender_nickname = Column(String(255), nullable=False)

    # 弹幕内容
    content = Column(Text, nullable=False)

    # 关联到某次直播间指标快照（可选）
    metric_id = Column(
        BigInteger,
        ForeignKey("live_room_metric.id"),
        nullable=True,
        index=True,
    )

    # 发送时间（爬取时间点）
    created_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, index=True
    )

    room = relationship("LiveRoomMetric", back_populates="danmu_messages")
