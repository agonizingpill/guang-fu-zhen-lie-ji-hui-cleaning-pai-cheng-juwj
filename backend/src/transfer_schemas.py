from pydantic import Field,field_validator
from .revisit_schemas import Inputs

class TransferInput(Inputs):
    transfer_code:str=Field(min_length=1,max_length=50)
    from_block_id:int
    to_block_id:int
    planned_liters:float=Field(gt=0,le=100000)
    gap_liters:float=Field(gt=0,le=100000)
    vehicle:str=Field(min_length=3,max_length=120)
    note:str=Field(default='',max_length=400)
    @field_validator('transfer_code','vehicle')
    @classmethod
    def nonempty(cls,v):
        if not v.strip():raise ValueError('不能为空')
        return v.strip()

class DispatchInput(Inputs):
    dispatched_liters:float=Field(gt=0,le=100000)
    loss_rate:float|None=Field(default=None,ge=0,lt=1)
    loss_note:str=Field(default='',max_length=400)
    request_key:str=Field(default='',max_length=80)

class ReceiptInput(Inputs):
    seq:int=Field(ge=1,le=200)
    received_liters:float=Field(gt=0,le=100000)
    note:str=Field(default='',max_length=400)
    request_key:str=Field(default='',max_length=80)

class ReturnInput(Inputs):
    returned_liters:float=Field(gt=0,le=100000)
    note:str=Field(min_length=3,max_length=400)
    request_key:str=Field(min_length=1,max_length=80)
    @field_validator('note')
    @classmethod
    def reason(cls,v):
        if len(v.strip())<3:raise ValueError('撤回原因至少3字')
        return v.strip()

class SettleInput(Inputs):
    loss_liters:float|None=Field(default=None,ge=0,le=100000)
    note:str=Field(default='',max_length=400)
    request_key:str=Field(default='',max_length=80)
