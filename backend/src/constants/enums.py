from enum import Enum
class Role(str, Enum):
    admin = 'admin'
    analyst = 'analyst'
    viewer = 'viewer'
class JobStatus(str, Enum):
    queued = 'queued'
    running = 'running'
    completed = 'completed'
    failed = 'failed'
class ReconStatus(str, Enum):
    # 来源尚未到齐或仍有未挂起差异
    open = 'open'
    # 差异均已采用来源处理，等待管理员一次性切换
    pending_confirmation = 'pending_confirmation'
    # 已切换为可研究批次
    confirmed = 'confirmed'
class DifferenceKind(str, Enum):
    missing = 'missing'        # 某站点时段仅一个来源有观测
    duplicate = 'duplicate'    # 同一来源同站点时段出现多条
    conflict = 'conflict'      # 两来源数值不一致
class DifferenceStatus(str, Enum):
    pending = 'pending'        # 挂起，等待处理
    resolved = 'resolved'      # 已采用某来源，等待批次确认
class SourceType(str, Enum):
    device = 'device'          # 设备文件
    console = 'console'        # 调度台
