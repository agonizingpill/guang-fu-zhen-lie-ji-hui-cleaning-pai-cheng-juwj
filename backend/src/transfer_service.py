import statistics
from datetime import datetime
from sqlalchemy import select
from fastapi import HTTPException
from .models import ArrayBlock
from .transfer_models import WaterTransfer,WaterTransferReceipt,WaterTransferReturn
from .field_service import require,audit

MIN_SAMPLES=3          # 少于该样本数时，损耗须由主管现场估量
MIN_MARGIN=0.01        # 每车次至少留出1个百分点的报损误差
MAX_RATE=0.95          # 保守损耗率上限
EPS=0.001
MAX_QUOTA=100000

def _round(value):return round(float(value),3)

def history(db,exclude=None):
    """从已结清调水单学习途中损耗；返回均值、离散度与保守损耗率。"""
    query=select(WaterTransfer).where(WaterTransfer.state=='settled',WaterTransfer.dispatched_liters>0)
    if exclude is not None:query=query.where(WaterTransfer.id!=exclude)
    rows=db.scalars(query).all()
    rates=[max(0.0,(item.loss_liters or 0.0)/item.dispatched_liters) for item in rows]
    if not rates:
        return {'sample_count':0,'mean_rate':None,'stdev':None,'margin':MIN_MARGIN,'conservative_rate':None}
    mean=statistics.fmean(rates)
    spread=statistics.pstdev(rates) if len(rates)>1 else 0.0
    margin=max(spread,MIN_MARGIN)
    return {'sample_count':len(rates),'mean_rate':round(mean,4),'stdev':round(spread,4),'margin':round(margin,4),'conservative_rate':round(min(MAX_RATE,mean+margin),4)}

def _rate_text(rate):
    return f'{rate*100:.1f}%'

def plan(db,body,user):
    source=require(db,ArrayBlock,body.from_block_id,True)
    target=require(db,ArrayBlock,body.to_block_id,True)
    if source.id==target.id:raise HTTPException(409,'调出与调入不能是同一阵列')
    if db.scalar(select(WaterTransfer).where(WaterTransfer.transfer_code==body.transfer_code)):raise HTTPException(409,'调水单号已存在')
    if body.planned_liters+EPS<body.gap_liters:raise HTTPException(409,'计划调水量低于缺口，扣除途中损耗后必然无法补足')
    stats=history(db)
    uses_history=stats['sample_count']>=MIN_SAMPLES
    conservative=_round(body.planned_liters*(1-stats['conservative_rate'])) if uses_history else None
    if conservative is not None and conservative+EPS<body.gap_liters:
        raise HTTPException(409,f'计划量按保守到水{conservative}L（损耗按{_rate_text(stats["conservative_rate"])}计）不足以补足缺口{body.gap_liters}L，请加大调水量')
    item=WaterTransfer(**body.model_dump(),created_by=user.email,
        loss_rate_used=stats['conservative_rate'] if uses_history else None,
        loss_source='history' if uses_history else 'manual_required',sample_count=stats['sample_count'],
        conservative_liters=conservative)
    db.add(item);audit(db,user,f'计划邻阵列调水 {body.transfer_code} {source.code}→{target.code} 计划{body.planned_liters}L 缺口{body.gap_liters}L');db.commit();return item

def revise(db,key,body,user):
    item=require(db,WaterTransfer,key,True)
    if item.state!='planned':raise HTTPException(409,'仅待发车调水单可修订，发车后计划冻结')
    if body.transfer_code!=item.transfer_code and db.scalar(select(WaterTransfer).where(WaterTransfer.transfer_code==body.transfer_code,WaterTransfer.id!=item.id)):
        raise HTTPException(409,'调水单号已存在')
    source=require(db,ArrayBlock,body.from_block_id);target=require(db,ArrayBlock,body.to_block_id)
    if source.id==target.id:raise HTTPException(409,'调出与调入不能是同一阵列')
    if body.planned_liters+EPS<body.gap_liters:raise HTTPException(409,'计划调水量低于缺口，扣除途中损耗后必然无法补足')
    for k,v in body.model_dump().items():setattr(item,k,v)
    stats=history(db,exclude=item.id)
    item.sample_count=stats['sample_count']
    if stats['sample_count']>=MIN_SAMPLES:
        item.conservative_liters=_round(item.planned_liters*(1-stats['conservative_rate']))
        item.loss_rate_used=stats['conservative_rate'];item.loss_source='history'
        if item.conservative_liters+EPS<item.gap_liters:
            raise HTTPException(409,f'修订后计划量按保守到水{item.conservative_liters}L不足以补足缺口{item.gap_liters}L，请加大调水量')
    else:
        item.conservative_liters=None;item.loss_rate_used=None;item.loss_source='manual_required'
    audit(db,user,f'修订调水单 {item.transfer_code} 计划{item.planned_liters}L 缺口{item.gap_liters}L');db.commit();return item

def dispatch(db,key,body,user):
    item=require(db,WaterTransfer,key,True)
    # 断线重试：同一请求键的原样重放直接返回，不再扣额
    if item.dispatch_key and body.request_key and item.dispatch_key==body.request_key.strip()[:80]:
        if abs(item.dispatched_liters-body.dispatched_liters)>EPS:raise HTTPException(409,'同一发车凭据键重复提交但水量不一致，请核对后刷新')
        return item
    if item.state!='planned':raise HTTPException(409,'仅待发车调水单可以发车，水量不得重复扣减')
    if body.dispatched_liters>item.planned_liters+EPS:raise HTTPException(409,'发车水量不得超过计划调水量')
    stats=history(db,exclude=item.id)
    if stats['sample_count']<MIN_SAMPLES:
        if body.loss_rate is None or len(body.loss_note.strip())<5:
            raise HTTPException(409,f'历史调水样本仅{stats["sample_count"]}条，请主管填写预计损耗率并说明估量依据（至少5字）')
        rate_used=min(MAX_RATE,body.loss_rate+MIN_MARGIN);source='manual';note=body.loss_note.strip();item.sample_count=stats['sample_count']
    else:
        rate_used=stats['conservative_rate'];source='history';note='';item.sample_count=stats['sample_count']
    conservative=_round(body.dispatched_liters*(1-rate_used))
    if conservative+EPS<item.gap_liters:
        raise HTTPException(409,f'按保守到水{conservative}L（损耗按{_rate_text(rate_used)}计）不足以补足缺口{item.gap_liters}L，请增加调水量或由主管重新估量')
    # 供水阵列加锁，扣额与清洗派工共用同一行锁，避免并发超扣
    source_block=db.scalar(select(ArrayBlock).where(ArrayBlock.id==item.from_block_id).with_for_update().execution_options(populate_existing=True))
    if not source_block:raise HTTPException(404,'现场记录不存在')
    if source_block.cleaning_state=='washing':raise HTTPException(409,'供水阵列正在清洗，配额已冻结，不可调出')
    if source_block.water_liters+EPS<body.dispatched_liters:raise HTTPException(409,f'供水阵列余水{source_block.water_liters}L不足，不能超扣配额')
    source_block.water_liters=_round(source_block.water_liters-body.dispatched_liters)
    item.dispatched_liters=body.dispatched_liters
    item.loss_rate_used=rate_used;item.loss_source=source;item.loss_note=note
    item.loss_rate=stats['mean_rate']
    item.conservative_liters=conservative
    item.state='dispatched';item.dispatched_by=user.email;item.dispatched_at=datetime.utcnow()
    if body.request_key:item.dispatch_key=body.request_key.strip()[:80]
    audit(db,user,f'调水发车 {item.transfer_code} 扣{source_block.code}{body.dispatched_liters}L 保守到水{conservative}L 余{source_block.water_liters}L');db.commit();return item

def estimate(db):return history(db)

def board(db):
    rows=db.scalars(select(WaterTransfer).order_by(WaterTransfer.id.desc())).all()
    receipts=db.scalars(select(WaterTransferReceipt).order_by(WaterTransferReceipt.transfer_id,WaterTransferReceipt.seq)).all()
    returns=db.scalars(select(WaterTransferReturn).order_by(WaterTransferReturn.transfer_id,WaterTransferReturn.id)).all()
    grouped={};returned={}
    for r in receipts:grouped.setdefault(r.transfer_id,[]).append(r)
    for r in returns:returned.setdefault(r.transfer_id,[]).append(r)
    return [{'transfer':item,'receipts':grouped.get(item.id,[]),'returns':returned.get(item.id,[])} for item in rows]

def receipts_of(db,key):
    require(db,WaterTransfer,key)
    return db.scalars(select(WaterTransferReceipt).where(WaterTransferReceipt.transfer_id==key).order_by(WaterTransferReceipt.seq)).all()

def receive(db,key,body,user):
    item=require(db,WaterTransfer,key,True)
    receipt_key=body.request_key.strip()[:80] if body.request_key else None
    if receipt_key:
        replay=db.scalar(select(WaterTransferReceipt).where(WaterTransferReceipt.transfer_id==item.id,WaterTransferReceipt.receipt_key==receipt_key))
        if replay:
            if abs(replay.received_liters-body.received_liters)>EPS:raise HTTPException(409,'同一收水凭据键重复提交但水量不一致，请核对后刷新')
            return replay
    if item.state!='dispatched':raise HTTPException(409,'须发车后逐车登记实收')
    existing=db.scalar(select(WaterTransferReceipt).where(WaterTransferReceipt.transfer_id==item.id,WaterTransferReceipt.seq==body.seq))
    if existing:
        if abs(existing.received_liters-body.received_liters)>EPS:raise HTTPException(409,f'第{body.seq}车已登记实收{existing.received_liters}L，不可改写；断线重试请提交相同水量')
        return existing
    remaining=_round(item.dispatched_liters-item.received_liters-item.returned_liters)
    if body.received_liters>remaining+EPS:raise HTTPException(409,f'超出本车发车余量：剩余{remaining}L，本次{body.received_liters}L 被拦下')
    target=db.scalar(select(ArrayBlock).where(ArrayBlock.id==item.to_block_id).with_for_update().execution_options(populate_existing=True))
    if not target:raise HTTPException(404,'现场记录不存在')
    if target.cleaning_state=='washing':raise HTTPException(409,'调入阵列正在清洗，配额冻结，请验收后重试入额')
    if target.water_liters+body.received_liters>MAX_QUOTA+EPS:raise HTTPException(409,'入额后超过阵列100000L配额上限')
    target.water_liters=_round(target.water_liters+body.received_liters)
    item.received_liters=_round(item.received_liters+body.received_liters)
    row=WaterTransferReceipt(transfer_id=item.id,seq=body.seq,receipt_key=receipt_key,received_liters=body.received_liters,received_by=user.email,note=body.note)
    db.add(row);audit(db,user,f'调水实收 {item.transfer_code} 第{body.seq}车{body.received_liters}L 入{target.code}余{target.water_liters}L');db.commit();return row

def return_water(db,key,body,user):
    item=require(db,WaterTransfer,key,True)
    request_key=body.request_key.strip()[:80]
    replay=db.scalar(select(WaterTransferReturn).where(WaterTransferReturn.transfer_id==item.id,WaterTransferReturn.return_key==request_key))
    if replay:
        if abs(replay.returned_liters-body.returned_liters)>EPS:raise HTTPException(409,'同一撤回凭据键重复提交但水量不一致，请核对后刷新')
        return item
    if item.state!='dispatched':raise HTTPException(409,'仅执行中的调水单可以撤回余水；结清后水量冻结')
    remaining=_round(item.dispatched_liters-item.received_liters-item.returned_liters)
    if body.returned_liters>remaining+EPS:raise HTTPException(409,f'只能退回点清的余水：当前可退{remaining}L，本次{body.returned_liters}L 被拦下')
    source=db.scalar(select(ArrayBlock).where(ArrayBlock.id==item.from_block_id).with_for_update().execution_options(populate_existing=True))
    if not source:raise HTTPException(404,'现场记录不存在')
    if source.water_liters+body.returned_liters>MAX_QUOTA+EPS:raise HTTPException(409,'退回后超过供水阵列100000L配额上限')
    source.water_liters=_round(source.water_liters+body.returned_liters)
    item.returned_liters=_round(item.returned_liters+body.returned_liters)
    item.returned_by=user.email;item.returned_at=datetime.utcnow();item.return_note=body.note;item.return_key=request_key
    db.add(WaterTransferReturn(transfer_id=item.id,return_key=request_key,returned_liters=body.returned_liters,returned_by=user.email,note=body.note))
    audit(db,user,f'调水撤回 {item.transfer_code} 退{body.returned_liters}L 回{source.code}余{source.water_liters}L 原因{body.note}');db.commit();return item

def settle(db,key,body,user):
    item=require(db,WaterTransfer,key,True)
    request_key=body.request_key.strip()[:80] if body.request_key else ''
    if request_key and item.settle_key and item.settle_key==request_key and item.state=='settled':
        if body.loss_liters is not None and abs(body.loss_liters-item.loss_liters)>EPS:raise HTTPException(409,'同一结清凭据键重复提交但损耗不一致，请核对后刷新')
        return item
    if item.state!='dispatched':raise HTTPException(409,'仅执行中的调水单可以结清，结清后凭据冻结')
    residual=_round(item.dispatched_liters-item.received_liters-item.returned_liters)
    if residual<-EPS:raise HTTPException(409,f'实收{item.received_liters}L与退水{item.returned_liters}L合计已超出发车{item.dispatched_liters}L，请先核对车次')
    if body.loss_liters is not None and abs(body.loss_liters-residual)>EPS:raise HTTPException(409,f'损耗{body.loss_liters}L与发车量对不上：发车{item.dispatched_liters}L − 实收{item.received_liters}L − 退水{item.returned_liters}L = {residual}L')
    item.loss_liters=_round(residual)
    item.loss_rate=round(residual/item.dispatched_liters,4) if item.dispatched_liters else 0.0
    item.state='settled';item.settled_by=user.email;item.settled_at=datetime.utcnow();item.settle_note=body.note
    if request_key:item.settle_key=request_key
    audit(db,user,f'调水结清 {item.transfer_code} 发车{item.dispatched_liters}L 实收{item.received_liters}L 退水{item.returned_liters}L 损耗{item.loss_liters}L');db.commit();return item
