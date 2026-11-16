from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from src.config.database import get_db
from src.models import ReconBatch, ReconDifference, SourceRecord, ReconRelease
from src.schemas.recon import SourceUpload, DifferenceResolve, ConfirmBatch
from src.middlewares.auth import current_user, can_write, admin_only
from src.services import recon
from src.services.audit import record
from src.utils.serialization import (recon_batch_dict, difference_dict,
                                     source_record_dict, release_dict)
router = APIRouter(prefix='/recon')


def _load_batch(db, batch_id):
    batch = db.get(ReconBatch, batch_id)
    if not batch:
        raise HTTPException(404, '对账批次不存在')
    return batch


@router.get('/batches')
def list_batches(db=Depends(get_db), u=Depends(current_user)):
    rows = db.scalars(select(ReconBatch).order_by(ReconBatch.id.desc()).limit(100))
    return [recon_batch_dict(b) for b in rows]


@router.post('/sources', status_code=201)
def upload(data: SourceUpload, db=Depends(get_db), u=Depends(can_write)):
    # 已确认批次收到补齐/重传：服务层只重开受影响批次，旧研究批次与任务固定不动
    batch, changed, reopened = recon.upload_source(db, data.batch_key, data.source,
                                                   data.source_ref, data.records)
    if reopened:
        record(db, u.email, 'recon.reopen', {'batch_id': batch.id, 'batch_key': batch.batch_key})
    record(db, u.email, 'recon.upload',
           {'batch_id': batch.id, 'source': data.source, 'changed': changed,
            'rows': len(data.records)})
    db.commit()
    return {**recon_batch_dict(batch), 'idempotent': not changed, 'reopened': reopened}


@router.get('/batches/{id}')
def batch_detail(id: int, db=Depends(get_db), u=Depends(current_user)):
    batch = _load_batch(db, id)
    diffs = db.scalars(select(ReconDifference).where(
        ReconDifference.batch_id == id).order_by(ReconDifference.kind, ReconDifference.station,
                                                 ReconDifference.period))
    records = db.scalars(select(SourceRecord).where(SourceRecord.batch_id == id))
    releases = db.scalars(select(ReconRelease).where(
        ReconRelease.batch_id == id).order_by(ReconRelease.id.desc()))
    return {**recon_batch_dict(batch),
            'differences': [difference_dict(d) for d in diffs],
            'sources': [source_record_dict(r) for r in records],
            'releases': [release_dict(r) for r in releases]}


@router.post('/batches/{id}/resolve')
def resolve(id: int, data: DifferenceResolve, db=Depends(get_db), u=Depends(can_write)):
    batch = _load_batch(db, id)
    if batch.status == 'confirmed':
        raise HTTPException(409, '批次已确认，请先重新上传来源重开后再调整差异')
    recon.resolve_differences(db, batch, data.items, u.email)
    record(db, u.email, 'recon.resolve',
           {'batch_id': id, 'items': len(data.items) or 'all'})
    db.commit()
    return recon_batch_dict(batch)


@router.post('/batches/{id}/confirm')
def confirm(id: int, data: ConfirmBatch, db=Depends(get_db), u=Depends(admin_only)):
    batch = _load_batch(db, id)
    before = batch.revision
    batch, dataset, created = recon.confirm(db, batch, u.email, data.note)
    record(db, u.email, 'recon.confirm',
           {'batch_id': id, 'dataset_id': dataset.id, 'created': created,
            'revision': batch.revision})
    db.commit()
    return {'batch': recon_batch_dict(batch), 'dataset_id': dataset.id,
            'dataset_revision': batch.revision, 'new_dataset': created,
            'pinned_previous_revision': before if (created and before != batch.revision) else None}
