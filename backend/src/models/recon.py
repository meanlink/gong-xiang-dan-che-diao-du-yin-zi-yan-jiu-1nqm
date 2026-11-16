from sqlalchemy import String, JSON, Double, ForeignKey, Boolean, Integer, UniqueConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base


class ReconBatch(Base):
    """日批对账批次：按日合并设备文件与调度台两来源，确认后才生成可研究数据批次。"""
    __tablename__ = 'recon_batches'
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_key: Mapped[str] = mapped_column(String(40), unique=True)  # 自然键，如 2026-11-16，重跑不新增
    status: Mapped[str] = mapped_column(String(30), default='open')
    # 已确认后再次补齐差异会自增版本；已运行/已批准任务始终固定在旧版本数据批次上
    revision: Mapped[int] = mapped_column(Integer, default=1)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[float] = mapped_column(Double)
    updated_at: Mapped[float] = mapped_column(Double)
    confirmed_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    confirmed_by: Mapped[str | None] = mapped_column(String(150), nullable=True)


class SourceRecord(Base):
    """来源观测明细。两来源各自留存，任何合并都不覆盖、不丢失原始记录。"""
    __tablename__ = 'source_records'
    __table_args__ = (UniqueConstraint('batch_id', 'source', 'station', 'period', 'seq',
                                       name='uq_source_natural_key'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('recon_batches.id'))
    source: Mapped[str] = mapped_column(String(20))          # device / console
    source_ref: Mapped[str] = mapped_column(String(200), default='')  # 文件名等上传凭据
    station: Mapped[str] = mapped_column(String(80))
    period: Mapped[int] = mapped_column(Integer)
    seq: Mapped[int] = mapped_column(Integer, default=0)     # 同键重复时的次序，重复记录各自保留
    payload: Mapped[dict] = mapped_column(JSON)              # 完整原始字段
    checksum: Mapped[str] = mapped_column(String(64))        # 单条指纹，重新上传同来源可幂等识别
    created_at: Mapped[float] = mapped_column(Double)


class ReconDifference(Base):
    """按站点+时段挂起的缺失、重复、数值冲突差异。"""
    __tablename__ = 'recon_differences'
    __table_args__ = (UniqueConstraint('batch_id', 'kind', 'station', 'period',
                                       name='uq_recon_difference_key'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('recon_batches.id'))
    kind: Mapped[str] = mapped_column(String(20))            # missing / duplicate / conflict
    station: Mapped[str] = mapped_column(String(80))
    period: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default='pending')  # pending / resolved
    detail: Mapped[dict] = mapped_column(JSON, default=dict)  # 两来源各自取值与重复条目
    resolution: Mapped[dict] = mapped_column(JSON, default=dict)  # 采用来源及处理人/时间
    created_at: Mapped[float] = mapped_column(Double)
    updated_at: Mapped[float] = mapped_column(Double)


class ReconRelease(Base):
    """批次去向：每次管理员确认生成（或复用）一个不可变研究数据批次。"""
    __tablename__ = 'recon_releases'
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('recon_batches.id'))
    revision: Mapped[int] = mapped_column(Integer)
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'))
    record_count: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[float] = mapped_column(Double)
    created_by: Mapped[str] = mapped_column(String(150))
    note: Mapped[str] = mapped_column(Text, default='')
