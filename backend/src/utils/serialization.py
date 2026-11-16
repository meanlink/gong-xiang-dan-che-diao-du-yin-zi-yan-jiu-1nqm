import hashlib, json
def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
def dataset_dict(d):
    return {'id':d.id, 'name':d.name, 'source':d.source, 'rows':len(d.records), 'checksum':d.checksum,
            'created_at':d.created_at, 'origin':getattr(d,'origin','manual'),
            'recon_batch_id':getattr(d,'recon_batch_id',None), 'revision':getattr(d,'revision',1)}
def recon_batch_dict(b):
    return {'id':b.id,'batch_key':b.batch_key,'status':b.status,'revision':b.revision,
            'stats':b.stats,'created_at':b.created_at,'updated_at':b.updated_at,
            'confirmed_at':b.confirmed_at,'confirmed_by':b.confirmed_by}
def difference_dict(d):
    return {'id':d.id,'batch_id':d.batch_id,'kind':d.kind,'station':d.station,'period':d.period,
            'status':d.status,'detail':d.detail,'resolution':d.resolution,
            'created_at':d.created_at,'updated_at':d.updated_at}
def source_record_dict(r):
    return {'id':r.id,'batch_id':r.batch_id,'source':r.source,'source_ref':r.source_ref,
            'station':r.station,'period':r.period,'seq':r.seq,'payload':r.payload,
            'checksum':r.checksum,'created_at':r.created_at}
def release_dict(r):
    return {'id':r.id,'batch_id':r.batch_id,'revision':r.revision,'dataset_id':r.dataset_id,
            'record_count':r.record_count,'checksum':r.checksum,'created_at':r.created_at,
            'created_by':r.created_by,'note':r.note}
def job_dict(j):
    return {k:getattr(j,k) for k in ['id','name','dataset_id','params','status','result','error','approved','created_at','finished_at']}
def report_dict(r):
    return {k:getattr(r,k) for k in ['id','name','job_id','destination','interval_seconds','next_run','enabled']}
def delivery_dict(d):
    return {k:getattr(d,k) for k in ['id','report_id','created_at','checksum','filename','destination']}
