from fastapi import APIRouter,Depends
from .database import session
from .auth import current,editor,admin
from .transfer_schemas import TransferInput,DispatchInput,ReceiptInput,ReturnInput,SettleInput
from . import transfer_service
router=APIRouter(prefix='/transfers')

@router.get('')
def transfers(user=Depends(current),db=Depends(session)):return transfer_service.board(db)
@router.get('/loss-estimate')
def loss_estimate(user=Depends(current),db=Depends(session)):return transfer_service.estimate(db)
@router.post('')
def plan(body:TransferInput,user=Depends(editor),db=Depends(session)):return transfer_service.plan(db,body,user)
@router.put('/{key}')
def revise(key:int,body:TransferInput,user=Depends(editor),db=Depends(session)):return transfer_service.revise(db,key,body,user)
@router.get('/{key}/receipts')
def receipts(key:int,user=Depends(current),db=Depends(session)):return transfer_service.receipts_of(db,key)
@router.post('/{key}/dispatch')
def dispatch(key:int,body:DispatchInput,user=Depends(admin),db=Depends(session)):return transfer_service.dispatch(db,key,body,user)
@router.post('/{key}/receipts')
def receive(key:int,body:ReceiptInput,user=Depends(editor),db=Depends(session)):return transfer_service.receive(db,key,body,user)
@router.post('/{key}/return')
def return_water(key:int,body:ReturnInput,user=Depends(admin),db=Depends(session)):return transfer_service.return_water(db,key,body,user)
@router.post('/{key}/settle')
def settle(key:int,body:SettleInput,user=Depends(admin),db=Depends(session)):return transfer_service.settle(db,key,body,user)
