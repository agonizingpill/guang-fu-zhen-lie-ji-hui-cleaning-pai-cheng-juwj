from datetime import datetime
from sqlalchemy import String,Float,ForeignKey,CheckConstraint,DateTime,UniqueConstraint,func
from sqlalchemy.orm import Mapped,mapped_column
from .database import Base

class WaterTransfer(Base):
    """邻阵列调水单：一次发车对应一张单据，分次收水在明细表留痕。"""
    __tablename__='water_transfers'
    __table_args__=(
        CheckConstraint('planned_liters>0 AND gap_liters>0'),
        CheckConstraint('dispatched_liters>=0 AND received_liters>=0 AND returned_liters>=0 AND loss_liters>=0'),
    )
    id:Mapped[int]=mapped_column(primary_key=True)
    transfer_code:Mapped[str]=mapped_column(String(50),unique=True)
    from_block_id:Mapped[int]=mapped_column(ForeignKey('array_blocks.id'))
    to_block_id:Mapped[int]=mapped_column(ForeignKey('array_blocks.id'))
    planned_liters:Mapped[float]=mapped_column(Float)
    gap_liters:Mapped[float]=mapped_column(Float)
    vehicle:Mapped[str]=mapped_column(String(120))
    note:Mapped[str]=mapped_column(String(400),default='')
    state:Mapped[str]=mapped_column(String(24),default='planned')
    dispatched_liters:Mapped[float]=mapped_column(Float,default=0)
    received_liters:Mapped[float]=mapped_column(Float,default=0)
    returned_liters:Mapped[float]=mapped_column(Float,default=0)
    loss_liters:Mapped[float]=mapped_column(Float,default=0)
    loss_rate:Mapped[float|None]=mapped_column(Float,nullable=True)
    loss_rate_used:Mapped[float|None]=mapped_column(Float,nullable=True)
    loss_source:Mapped[str]=mapped_column(String(16),default='')
    loss_note:Mapped[str]=mapped_column(String(400),default='')
    sample_count:Mapped[int]=mapped_column(default=0)
    conservative_liters:Mapped[float|None]=mapped_column(Float,nullable=True)
    created_by:Mapped[str]=mapped_column(String(120),default='')
    dispatch_key:Mapped[str]=mapped_column(String(80),default='')
    dispatched_by:Mapped[str]=mapped_column(String(120),default='')
    dispatched_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    return_key:Mapped[str]=mapped_column(String(80),default='')
    returned_by:Mapped[str]=mapped_column(String(120),default='')
    returned_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    return_note:Mapped[str]=mapped_column(String(400),default='')
    settled_by:Mapped[str]=mapped_column(String(120),default='')
    settled_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    settle_note:Mapped[str]=mapped_column(String(400),default='')
    settle_key:Mapped[str]=mapped_column(String(80),default='')
    created_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now())

class WaterTransferReceipt(Base):
    """分次收水：每次收水必须有车次序号，唯一约束保证断线重试不会重复入额。"""
    __tablename__='water_transfer_receipts'
    __table_args__=(
        UniqueConstraint('transfer_id','seq',name='uq_transfer_receipt_seq'),
        UniqueConstraint('transfer_id','receipt_key',name='uq_transfer_receipt_key'),
        CheckConstraint('seq>=1 AND received_liters>0'),
    )
    id:Mapped[int]=mapped_column(primary_key=True)
    transfer_id:Mapped[int]=mapped_column(ForeignKey('water_transfers.id'))
    seq:Mapped[int]=mapped_column()
    receipt_key:Mapped[str|None]=mapped_column(String(80),nullable=True,default=None)
    received_liters:Mapped[float]=mapped_column(Float)
    received_by:Mapped[str]=mapped_column(String(120))
    note:Mapped[str]=mapped_column(String(400),default='')
    created_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now())

class WaterTransferReturn(Base):
    """撤回点清余水：每条退回凭据唯一，断线重试不会重复退回。"""
    __tablename__='water_transfer_returns'
    __table_args__=(
        UniqueConstraint('transfer_id','return_key',name='uq_transfer_return_key'),
        CheckConstraint('returned_liters>0'),
    )
    id:Mapped[int]=mapped_column(primary_key=True)
    transfer_id:Mapped[int]=mapped_column(ForeignKey('water_transfers.id'))
    return_key:Mapped[str]=mapped_column(String(80))
    returned_liters:Mapped[float]=mapped_column(Float)
    returned_by:Mapped[str]=mapped_column(String(120))
    note:Mapped[str]=mapped_column(String(400),default='')
    created_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now())
