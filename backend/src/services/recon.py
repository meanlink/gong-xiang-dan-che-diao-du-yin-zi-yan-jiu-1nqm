"""日批对账：设备文件与调度台两来源按站点+时段核对。

设计要点：
- 来源明细各自持久化，任何合并都不覆盖原始记录（不丢数据）。
- 缺失/重复/数值冲突全部挂起，未确认数据与研究侧物理隔离，分析任务只能选到已确认批次。
- 以 batch_key、来源指纹与差异自然键保证幂等：重跑同日批次、重传同一来源不新增记录，
  失败后续跑不会重复生成研究批次。
- 已运行/已批准任务绑定旧的不可变数据批次；补齐差异只重开受影响批次并生成新版本。
"""
import math
import time
from contextlib import contextmanager

from fastapi import HTTPException
from redis import Redis
from sqlalchemy import select, delete, func

from src.config.settings import REDIS_URL
from src.models import Dataset, ReconBatch, SourceRecord, ReconDifference, ReconRelease
from src.services.business import metadata
from src.utils.serialization import checksum

COMPARE_COLUMNS = ('commute', 'arrivals', 'demand')
TOLERANCE = 1e-9
SOURCES = ('device', 'console')
SOURCE_LABEL = {'device': '设备文件', 'console': '调度台'}


@contextmanager
def batch_lock(batch_key):
    """同一日批串行化，避免对账与研究/并发上传相互混入未确认数据。Redis 不可用时退化为无锁，
    数据库唯一约束仍是最后防线。"""
    key = f'recon:lock:{batch_key}'
    redis = None
    try:
        redis = Redis.from_url(REDIS_URL, socket_timeout=3)
        if not redis.set(key, '1', nx=True, ex=60):
            raise HTTPException(409, '该日批正在对账处理中，请稍后重试')
    except HTTPException:
        if redis is not None:
            redis.close()
        raise
    except Exception:
        # Redis 故障不阻断业务；事务与唯一约束保证不产生重复/脏数据
        redis = None
    try:
        yield
    finally:
        if redis is not None:
            try:
                redis.delete(key)
                redis.close()
            except Exception:
                pass


def _validate_rows(rows):
    columns = metadata()['columns']
    cleaned = []
    for index, row in enumerate(rows):
        item = dict(row)
        for c in columns:
            value = item.get(c['key'])
            if value is None or value == '':
                raise HTTPException(422, f'第 {index + 1} 行缺少字段 {c["label"]}')
            if c['type'] == 'number':
                try:
                    if isinstance(value, bool) or not math.isfinite(float(value)):
                        raise ValueError()
                    item[c['key']] = float(value)
                except (TypeError, ValueError, OverflowError):
                    raise HTTPException(422, f'第 {index + 1} 行 {c["label"]} 必须为有限数值')
            else:
                item[c['key']] = str(value).strip()
                if not item[c['key']]:
                    raise HTTPException(422, f'第 {index + 1} 行 {c["label"]} 不能为空')
        if item['arrivals'] < 0 or item['demand'] < 0:
            raise HTTPException(422, f'第 {index + 1} 行客流与需求不能为负数')
        item['period'] = int(item['period'])
        cleaned.append(item)
    return cleaned


def _record_fingerprint(row):
    return checksum({k: row[k] for k in ('station', 'period', 'commute', 'arrivals', 'demand')})


def _get_or_create_batch(db, batch_key):
    batch = db.scalar(select(ReconBatch).where(ReconBatch.batch_key == batch_key))
    if batch is None:
        now = time.time()
        batch = ReconBatch(batch_key=batch_key, status='open', revision=1,
                           stats={}, created_at=now, updated_at=now)
        db.add(batch)
        db.flush()
    return batch


def upload_source(db, batch_key, source, source_ref, raw_rows):
    if source not in SOURCES:
        raise HTTPException(422, '来源仅支持 device（设备文件）或 console（调度台）')
    rows = _validate_rows(raw_rows)
    with batch_lock(batch_key):
        batch = _get_or_create_batch(db, batch_key)
        now = time.time()
        existing = list(db.scalars(
            select(SourceRecord).where(SourceRecord.batch_id == batch.id,
                                       SourceRecord.source == source)))
        # 整来源指纹一致 => 重新上传同一来源，幂等返回，不新增任何记录，也不重开已确认批次
        new_fingerprint = checksum(sorted((_record_fingerprint(r) for r in rows)))
        old_fingerprint = checksum(sorted(r.checksum for r in existing)) if existing else None
        if existing and new_fingerprint == old_fingerprint:
            return batch, False, False
        reopened = batch.status == 'confirmed'
        if reopened:
            # 已确认批次收到补齐/修正：只重开本批次，旧研究批次与已运行/批准任务固定不动
            reopen_if_needed(batch)
        # 来源被重新上传（含修正）：先移除该来源旧明细，再写入新明细，另一来源保持不动，不覆盖
        if existing:
            db.execute(delete(SourceRecord).where(SourceRecord.batch_id == batch.id,
                                                  SourceRecord.source == source))
            db.flush()
        # 同站同时段按上报顺序保留，重复条目各自留存，用 seq 区分，不互相覆盖
        grouped = {}
        for row in rows:
            grouped.setdefault((row['station'], row['period']), []).append(row)
        for (station, period), items in sorted(grouped.items()):
            for seq, row in enumerate(items):
                db.add(SourceRecord(batch_id=batch.id, source=source, source_ref=source_ref or '',
                                    station=station, period=period, seq=seq, payload=row,
                                    checksum=_record_fingerprint(row), created_at=now))
        db.flush()
        recompute(db, batch)
        db.flush()
        return batch, True, reopened


def _values_equal(a, b):
    return all(abs(float(a[k]) - float(b[k])) <= TOLERANCE for k in COMPARE_COLUMNS)


def _upsert_difference(db, batch_id, kind, station, period, detail, now):
    diff = db.scalar(select(ReconDifference).where(
        ReconDifference.batch_id == batch_id, ReconDifference.kind == kind,
        ReconDifference.station == station, ReconDifference.period == period))
    if diff is None:
        diff = ReconDifference(batch_id=batch_id, kind=kind, station=station, period=period,
                               status='pending', detail=detail, resolution={},
                               created_at=now, updated_at=now)
        db.add(diff)
    else:
        diff.detail = detail
        diff.status = 'pending'
        diff.resolution = {}
        diff.updated_at = now
    return diff


def recompute(db, batch):
    """依据当前两来源明细重新挂起差异。已确认批次收到新数据时被重开（revision 不变，确认后再升版）。"""
    now = time.time()
    records = list(db.scalars(select(SourceRecord).where(SourceRecord.batch_id == batch.id)))
    grouped = {}
    for r in records:
        grouped.setdefault((r.station, r.period), {}).setdefault(r.source, []).append(r)

    db.execute(delete(ReconDifference).where(ReconDifference.batch_id == batch.id))
    db.flush()
    counts = {'missing': 0, 'duplicate': 0, 'conflict': 0}
    sources_seen = sorted({r.source for r in records})

    for (station, period), by_source in sorted(grouped.items()):
        present = [s for s in SOURCES if s in by_source]
        # 缺失：仅一个来源有该站点时段
        if len(present) == 1:
            only = present[0]
            rec = by_source[only][0]
            counts['missing'] += 1
            _upsert_difference(db, batch.id, 'missing', station, period, {
                'present_source': only,
                'present_label': SOURCE_LABEL[only],
                'present_record': rec.payload,
                'absent_source': [s for s in SOURCES if s != only][0],
                'absent_label': SOURCE_LABEL[[s for s in SOURCES if s != only][0]],
            }, now)
        # 重复：任一来源同站同时段多条，全部保留，不互相覆盖
        for source in present:
            items = by_source[source]
            if len(items) > 1:
                counts['duplicate'] += 1
                _upsert_difference(db, batch.id, 'duplicate', station, period, {
                    'source': source, 'source_label': SOURCE_LABEL[source],
                    'candidates': [{'seq': r.seq, 'record': r.payload, 'checksum': r.checksum}
                                   for r in sorted(items, key=lambda r: r.seq)],
                }, now)
        # 数值冲突：两来源都有且取值不一致（各取首条比较）
        if len(present) == 2:
            device_rec = by_source['device'][0]
            console_rec = by_source['console'][0]
            if not _values_equal(device_rec.payload, console_rec.payload):
                mismatched = [k for k in COMPARE_COLUMNS
                              if abs(float(device_rec.payload[k]) - float(console_rec.payload[k])) > TOLERANCE]
                counts['conflict'] += 1
                _upsert_difference(db, batch.id, 'conflict', station, period, {
                    'device': device_rec.payload, 'console': console_rec.payload,
                    'mismatched_columns': mismatched,
                }, now)

    pending_total = sum(counts.values())
    batch.stats = {
        'sources': sources_seen,
        'source_counts': {s: sum(1 for r in records if r.source == s) for s in SOURCES},
        'station_period_keys': len(grouped),
        'counts': counts,
        'pending': pending_total,
    }
    batch.updated_at = now
    if pending_total == 0 and len(sources_seen) == 2:
        # 干净批次：无挂起差异，直接等待管理员一次性确认切换
        batch.status = 'pending_confirmation'
    else:
        batch.status = 'open'
    return batch


def resolve_differences(db, batch, items, actor):
    """按差异逐个采用来源。可一次性处理全部挂起差异；只记录决定，不改动来源明细。"""
    now = time.time()
    # 兼容 HTTP 层的 pydantic 模型与脚本层的 dict
    items = [it.model_dump() if hasattr(it, 'model_dump') else dict(it) for it in items]
    diffs = {d.id: d for d in db.scalars(
        select(ReconDifference).where(ReconDifference.batch_id == batch.id))}
    targets = list(diffs.values()) if not items else [diffs.get(it.get('id')) for it in items]
    if any(d is None for d in targets):
        raise HTTPException(404, '存在不属于该日批或已失效的差异，请刷新后重试')
    choice_by_id = {it.get('id'): it.get('adopt') for it in items} if items else {}
    seq_by_id = {it.get('id'): it.get('seq') for it in items} if items else {}
    for d in targets:
        if d.status == 'resolved':
            continue
        adopt = choice_by_id.get(d.id) or _default_adopt(d)
        _validate_adoption(d, adopt)
        seq = 0
        if d.kind == 'duplicate':
            seq = seq_by_id.get(d.id)
            valid_seqs = [c['seq'] for c in d.detail['candidates']]
            if seq is None:
                seq = 0
            if seq not in valid_seqs:
                raise HTTPException(422, '重复差异须指定有效的条目序号 seq')
        d.status = 'resolved'
        d.resolution = {'adopt': adopt, 'adopt_label': SOURCE_LABEL.get(adopt, adopt),
                        'by': actor, 'at': now, **({'seq': seq} if d.kind == 'duplicate' else {})}
        d.updated_at = now
    db.flush()
    pending = db.scalar(select(ReconDifference).where(
        ReconDifference.batch_id == batch.id, ReconDifference.status == 'pending'))
    if pending is None and batch.stats.get('sources') and len(batch.stats['sources']) == 2:
        batch.status = 'pending_confirmation'
    else:
        batch.status = 'open'
    batch.updated_at = now
    return batch


def _default_adopt(diff):
    if diff.kind == 'missing':
        return diff.detail['present_source']
    if diff.kind == 'duplicate':
        return diff.detail['source']
    return 'device'


def _validate_adoption(diff, adopt):
    if diff.kind == 'missing':
        if adopt != diff.detail['present_source']:
            raise HTTPException(422, '缺失差异只能采用实际存在观测的来源')
    elif diff.kind == 'duplicate':
        if adopt != diff.detail['source']:
            raise HTTPException(422, '重复差异采用来源须与上报来源一致，另以 seq 指定条目')
    elif adopt not in SOURCES:
        raise HTTPException(422, '冲突差异须采用 device 或 console')


def _canonical_records(db, batch):
    """依据已采用来源生成规范化研究记录；仍有挂起差异或来源未到齐时拒绝，未确认数据绝不进入研究侧。"""
    if len(batch.stats.get('sources', [])) < 2:
        raise HTTPException(409, '需设备文件与调度台两来源到齐后才能确认')
    diffs = list(db.scalars(select(ReconDifference).where(ReconDifference.batch_id == batch.id)))
    pending = [d for d in diffs if d.status == 'pending']
    if pending:
        raise HTTPException(409, f'仍有 {len(pending)} 项差异挂起，无法切换为研究批次')
    records = list(db.scalars(select(SourceRecord).where(SourceRecord.batch_id == batch.id)))
    grouped = {}
    for r in records:
        grouped.setdefault((r.station, r.period), {}).setdefault(r.source, []).append(r)
    resolved_map = {(d.kind, d.station, d.period): d for d in diffs}
    canonical = []
    for (station, period), by_source in sorted(grouped.items()):
        chosen_source, chosen_seq = None, 0
        conflict = resolved_map.get(('conflict', station, period))
        duplicate = resolved_map.get(('duplicate', station, period))
        missing = resolved_map.get(('missing', station, period))
        if conflict is not None:
            chosen_source = conflict.resolution['adopt']
        elif missing is not None:
            chosen_source = missing.resolution['adopt']
        else:
            chosen_source = 'device' if 'device' in by_source else 'console'
        if duplicate is not None and duplicate.detail['source'] == chosen_source:
            chosen_seq = duplicate.resolution.get('seq', 0)
        candidates = by_source.get(chosen_source, [])
        chosen = next((r for r in candidates if r.seq == chosen_seq), candidates[0])
        row = dict(chosen.payload)
        row['period'] = int(row['period'])
        canonical.append(row)
    canonical.sort(key=lambda r: (r['station'], r['period']))
    return canonical


def confirm(db, batch, actor, note=''):
    """管理员确认差异后一次性切换为可研究批次。内容未变则复用既有批次，不重复生成。
    已确认批次重复确认（含失败续跑）幂等返回当前研究批次。"""
    now = time.time()
    if batch.status == 'confirmed':
        release = db.scalar(select(ReconRelease).where(
            ReconRelease.batch_id == batch.id).order_by(ReconRelease.id.desc()))
        if release is not None:
            return batch, db.get(Dataset, release.dataset_id), False
        raise HTTPException(409, '该日批缺少去向记录，请重新上传来源后再确认')
    canonical = _canonical_records(db, batch)
    fingerprint = checksum(canonical)
    release = db.scalar(select(ReconRelease).where(
        ReconRelease.batch_id == batch.id, ReconRelease.checksum == fingerprint))
    if release is not None:
        # 失败续跑/重复确认：内容相同，复用原研究批次，不新增 Dataset/Release
        dataset = db.get(Dataset, release.dataset_id)
        batch.status = 'confirmed'
        batch.confirmed_at = now
        batch.confirmed_by = actor
        batch.updated_at = now
        return batch, dataset, False
    # 已有过历史去向 => 这是补齐差异后的再次确认，升版；首次确认保持 v1
    prior_releases = db.scalar(select(func.count()).select_from(ReconRelease).where(
        ReconRelease.batch_id == batch.id))
    revision = batch.revision + (1 if prior_releases else 0)
    name = f"日批对账 · {batch.batch_key} · 研究批次 v{revision}"
    base, suffix = name, 1
    while db.scalar(select(Dataset).where(Dataset.name == name)):
        suffix += 1
        name = f'{base}（{suffix}）'
    dataset = Dataset(name=name, source=f'recon:{batch.batch_key}', records=canonical,
                      checksum=fingerprint, created_at=now, origin='recon',
                      recon_batch_id=batch.id, revision=revision)
    db.add(dataset)
    db.flush()
    release = ReconRelease(batch_id=batch.id, revision=revision, dataset_id=dataset.id,
                           record_count=len(canonical), checksum=fingerprint,
                           created_at=now, created_by=actor, note=note or '')
    db.add(release)
    batch.status = 'confirmed'
    batch.revision = revision
    batch.confirmed_at = now
    batch.confirmed_by = actor
    batch.updated_at = now
    db.flush()
    return batch, dataset, True


def reopen_if_needed(batch):
    """已确认批次收到补齐/修正数据后重开；旧研究批次与绑定的任务保持不动。"""
    if batch.status == 'confirmed':
        batch.status = 'open'
        batch.confirmed_at = None
        batch.confirmed_by = None
    return batch
