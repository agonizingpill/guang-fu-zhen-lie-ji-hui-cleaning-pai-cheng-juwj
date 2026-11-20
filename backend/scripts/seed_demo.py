from datetime import datetime,timedelta
from sqlalchemy import select,func
from src.database import Base,engine,Session
from src.models import User,ArrayBlock,SoilingSurvey,WashMission
from src.revisit_models import WaterDelivery,FollowupSurvey
from src.transfer_models import WaterTransfer
from src.auth import hash_password
from src.operations_models import WashCrew

def seed():
    Base.metadata.create_all(engine)
    with Session() as db:
        for role in ['admin','planner','viewer']:
            email=role+'@qingling.test'
            if not db.scalar(select(User).where(User.email==email)):db.add(User(email=email,password=hash_password('Solar2026!'),role=role))
        for code,minutes in [('CREW-SOUTH',480),('CREW-RIDGE',360)]:
            if not db.scalar(select(WashCrew).where(WashCrew.code==code)):db.add(WashCrew(code=code,max_daily_minutes=minutes))
        blocks=[('SL-A01','南坡一号','南坡',150,23,780,1500),('SL-A02','南坡二号','南坡',120,25,630,1200),('SL-B01','脊线一号','脊线',100,18,520,900),('SL-C01','西坡一号','西坡',80,30,420,600)]
        for code,name,sector,cap,slope,area,water in blocks:
            if not db.scalar(select(ArrayBlock).where(ArrayBlock.code==code)):db.add(ArrayBlock(code=code,name=name,sector=sector,capacity_kw=cap,slope=slope,area_m2=area,water_liters=water))
        db.flush();rows=db.scalars(select(ArrayBlock).order_by(ArrayBlock.id)).all()
        measurements=[('SV-1117-A01',rows[0],800,35,18,3.2,88),('SV-1117-A02',rows[1],820,33,12,2.1,76),('SV-CLOUD-01',rows[2],240,23,8,1.2,18)]
        for code,block,irr,temp,rain,dust,power in measurements:
            if not db.scalar(select(SoilingSurvey).where(SoilingSurvey.code==code)):db.add(SoilingSurvey(code=code,block_id=block.id,capacity_kw=block.capacity_kw,slope=block.slope,irradiance=irr,module_temp=temp,rain_days=rain,dust=dust,observed_kw=power,state='recorded'))
        db.flush()
        block=db.scalar(select(ArrayBlock).where(ArrayBlock.code=='SL-C01'))
        if not db.scalar(select(WaterDelivery).where(WaterDelivery.delivery_code=='WD-DEMO-01')):
            db.add(WaterDelivery(block_id=block.id,delivery_code='WD-DEMO-01',liters=500,source='西坡蓄水池 / 水车02'))
        historical=db.scalar(select(SoilingSurvey).where(SoilingSurvey.code=='SV-DEMO-CLEAN'))
        if not historical:
            historical=SoilingSurvey(code='SV-DEMO-CLEAN',block_id=block.id,capacity_kw=block.capacity_kw,slope=block.slope,irradiance=800,module_temp=35,rain_days=15,dust=2,observed_kw=50,clean_kw=62,predicted_loss=12,recommended_water=100,state='closed')
            db.add(historical);db.flush()
        mission=db.scalar(select(WashMission).where(WashMission.survey_id==historical.id))
        if not mission:
            mission=WashMission(survey_id=historical.id,water_liters=100,available_liters=700,status='accepted',post_kw=62,post_irradiance=800,normalized_kw=62,verified_gain=12,dispatched_at=datetime.utcnow()-timedelta(days=7),accepted_at=datetime.utcnow()-timedelta(days=7))
            db.add(mission);db.flush()
        if not db.scalar(select(FollowupSurvey).where(FollowupSurvey.mission_id==mission.id,FollowupSurvey.days_after==2)):
            db.add(FollowupSurvey(mission_id=mission.id,days_after=2,irradiance=800,observed_kw=61,normalized_kw=61,normalized_loss=100/62,state='stable',baseline_snapshot={'post_kw':62,'post_irradiance':800,'accepted_at':mission.accepted_at.isoformat(),'block_id':block.id,'block_code':block.code,'survey_id':historical.id,'survey_code':historical.code,'threshold_pct':5}))
        ridge=db.scalar(select(ArrayBlock).where(ArrayBlock.code=='SL-B01'))
        south=db.scalar(select(ArrayBlock).where(ArrayBlock.code=='SL-A01'))
        if ridge and south:
            history=[('WT-DEMO-H1',400,0.05,4),('WT-DEMO-H2',350,0.06,3),('WT-DEMO-H3',450,0.07,2)]
            for code,liters,rate,days in history:
                if db.scalar(select(WaterTransfer).where(WaterTransfer.transfer_code==code)):continue
                received=round(liters*(1-rate),3)
                db.add(WaterTransfer(transfer_code=code,from_block_id=ridge.id,to_block_id=south.id,planned_liters=liters,gap_liters=round(received-20,3),
                    vehicle='水车05 / 邻阵列短驳',note='历史结清调水，用于学习途中损耗',state='settled',
                    dispatched_liters=liters,received_liters=received,returned_liters=0,loss_liters=round(liters-received,3),loss_rate=rate,
                    loss_rate_used=rate,loss_source='history',sample_count=0,conservative_liters=round(received-5,3),
                    created_by='planner@qingling.test',dispatched_by='admin@qingling.test',dispatched_at=datetime.utcnow()-timedelta(days=days),
                    settled_by='admin@qingling.test',settled_at=datetime.utcnow()-timedelta(days=days)))
            if not db.scalar(select(WaterTransfer).where(WaterTransfer.transfer_code=='WT-DEMO-02')):
                db.add(WaterTransfer(transfer_code='WT-DEMO-02',from_block_id=ridge.id,to_block_id=south.id,planned_liters=600,gap_liters=520,
                    vehicle='水车05 / 邻阵列短驳',note='南坡一号清洗配额不足，等待主管发车',state='planned',created_by='planner@qingling.test'))
        db.commit();print({key:db.scalar(select(func.count()).select_from(model)) for key,model in [('users',User),('blocks',ArrayBlock),('surveys',SoilingSurvey)]})
if __name__=='__main__':seed()
