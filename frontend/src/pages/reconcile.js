import {recon} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {esc,fmt,date,notify} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
import {parseCSV} from '../utils/csv.js';
import {ReconStatus,DifferenceKind,DifferenceStatus} from '../constants/enums.js';

export async function reconcilePage(id){
 workspace.reconBatches=await recon.batches();
 const first=id?workspace.reconBatches.find(b=>b.id===Number(id)):workspace.reconBatches[0];
 workspace.reconSelected=first?await recon.batch(first.id):null;
 const canWrite=session.user.role!=='viewer';
 const b=workspace.reconSelected;
 return heading('03 / DAILY RECON','日批对账与批次切换','设备文件与调度台按站点+时段核对；缺失、重复、数值冲突先挂起，来源原始记录全程留存，负责人确认后才一次性切换为可研究批次。')
 +'<div class="dataset-grid"><section class="panel"><div class="section-title"><h2>对账日批</h2><span>'+workspace.reconBatches.length+' 批</span></div><div class="batch-list">'
 +(workspace.reconBatches.map(x=>'<button class="batch-item'+(b&&x.id===b.id?' active':'')+'" data-batch="'+x.id+'"><strong>'+esc(x.batch_key)+'</strong><span>'+esc(ReconStatus[x.status]||x.status)+' · v'+x.revision+'</span><small>挂起 '+((x.stats&&x.stats.pending)||0)+' 项 · 两来源 '+(x.stats?x.stats.source_counts.device:0)+'/'+(x.stats?x.stats.source_counts.console:0)+'</small></button>').join('')||'<p class="empty">尚无日批，请先上传任一来源。</p>')
 +'</div><div class="section-title"><h2>上传来源观测</h2></div><form id="recon-form"><label>日批键（日期）<input name="batch_key" required placeholder="例如 2026-11-16" value="'+esc(b?b.batch_key:new Date().toISOString().slice(0,10))+'"></label><label>来源<select name="source"><option value="device">设备文件</option><option value="console">调度台</option></select></label><label>上传 CSV 或 JSON<input type="file" id="recon-file" accept=".json,.csv"></label><label>记录 JSON<textarea name="records" rows="5" placeholder="粘贴 JSON 数组，或先选择上方文件" required></textarea></label><p class="hint">同来源重传且内容一致时幂等忽略；已确认批次收到新数据只重开本批，旧研究批次与任务固定。</p><button type="submit" class="primary" '+(canWrite?'':'disabled')+'>核对并入账 ↗</button></form></section>'
 +'<section class="panel">'+(b?batchDetail(b,canWrite):'<div class="empty">选择左侧日批查看差异、采用来源与批次去向。</div>')+'</section></div>';
}

function batchDetail(b,canWrite){
 const c=b.stats&&b.stats.counts?b.stats.counts:{missing:0,duplicate:0,conflict:0};
 const pending=b.differences.filter(d=>d.status==='pending');
 const isAdmin=session.user.role==='admin';
 return '<div class="section-title"><h2>'+esc(b.batch_key)+' · v'+b.revision+'</h2><span class="status '+esc(b.status)+'">'+esc(ReconStatus[b.status]||b.status)+'</span></div>'
 +'<div class="metrics">'+[['设备文件',b.stats?b.stats.source_counts.device:0,'条'],['调度台',b.stats?b.stats.source_counts.console:0,'条'],['缺失',c.missing,'项'],['重复',c.duplicate,'项'],['数值冲突',c.conflict,'项']].map(m=>'<div><span>'+m[0]+'</span><strong>'+fmt(m[1])+'</strong><small>'+m[2]+'</small></div>').join('')+'</div>'
 +'<div class="section-title" style="margin-top:24px"><h2>挂起差异（按站点 / 时段）</h2><span>'+pending.length+' 项待处理</span></div>'
 +(b.differences.length?diffTable(b):'<p class="empty">两来源核对一致，无差异。</p>')
 +(pending.length&&canWrite?'<div class="recon-actions"><button class="button" id="resolve-all">一次性采用全部挂起差异（默认来源）</button></div>':'')
 +'<div class="section-title" style="margin-top:26px"><h2>确认切换</h2><span>仅业务负责人</span></div>'
 +'<div class="confirm-row"><input id="confirm-note" placeholder="切换说明（可选）" maxlength="500" '+(b.status==='confirmed'||!isAdmin?'disabled':'')+'><button class="primary" id="confirm-batch" '+(b.status!=='pending_confirmation'||!isAdmin?'disabled':'')+'>一次性切换为可研究批次 ↗</button></div>'
 +(b.status==='confirmed'?'<p class="hint">已确认。重新上传任一来源将只重开本批次并生成新版本，已运行/已批准任务仍固定在原批次。</p>':'')
 +'<div class="section-title" style="margin-top:26px"><h2>批次去向</h2><span>'+b.releases.length+' 个研究批次</span></div>'
 +(b.releases.length?releaseTable(b):'<p class="empty">确认后在此生成不可变研究批次，并可在分析工作台选用。</p>')
 +'<p class="hint">来源明细共 '+b.sources.length+' 条，全部独立留存、不被合并覆盖；单条指纹随记录保存。</p>';
}

function diffTable(b){
 return '<div class="table-wrap recon-diffs"><table><thead><tr><th>类型</th><th>站点</th><th>时段</th><th>状态</th><th>两来源取值</th><th>采用来源</th></tr></thead><tbody>'
 +b.differences.map(d=>'<tr class="'+esc(d.status)+'"><td><span class="diff-tag '+esc(d.kind)+'">'+esc(DifferenceKind[d.kind])+'</span></td><td>'+esc(d.station)+'</td><td>'+fmt(d.period)+'</td><td>'+esc(DifferenceStatus[d.status]||d.status)+(d.resolution&&d.resolution.adopt?' · '+esc(d.resolution.adopt_label):'')+'</td><td class="compare-cell">'+compareText(d)+'</td><td>'+adoptControl(d)+'</td></tr>').join('')
 +'</tbody></table></div>';
}

function compareText(d){
 if(d.kind==='missing'){const r=d.detail.present_record;return esc(d.detail.present_label)+' 有：'+esc(metricLine(r))+'<br><span class="muted">'+esc(d.detail.absent_label)+' 缺失</span>';}
 if(d.kind==='duplicate'){return d.detail.candidates.map(c=>'<span class="muted">#'+c.seq+'</span> '+esc(metricLine(c.record))).join('<br>');}
 const dev=d.detail.device,con=d.detail.console;
 return '<span class="muted">设备</span> '+esc(metricLine(dev))+'<br><span class="muted">调度台</span> '+esc(metricLine(con));
}

function metricLine(r){return '通勤 '+fmt(r.commute)+' / 客流 '+fmt(r.arrivals)+' / 需求 '+fmt(r.demand);}

function adoptControl(d){
 if(d.status==='resolved'){return '<span class="muted">已采用 '+esc(d.resolution.adopt_label)+(d.resolution.seq!=null?' #'+d.resolution.seq:'')+'</span>';}
 if(session.user.role==='viewer'){return '<span class="muted">只读</span>';}
 if(d.kind==='missing'){return '<button class="button small" data-resolve="'+d.id+'" data-adopt="'+esc(d.detail.present_source)+'">采用 '+esc(d.detail.present_label)+'</button>';}
 if(d.kind==='duplicate'){return d.detail.candidates.map(c=>'<button class="button small" data-resolve="'+d.id+'" data-adopt="'+esc(d.detail.source)+'" data-seq="'+c.seq+'">采用 #'+c.seq+'</button>').join(' ');}
 return '<button class="button small" data-resolve="'+d.id+'" data-adopt="device">采用设备</button> <button class="button small" data-resolve="'+d.id+'" data-adopt="console">采用调度台</button>';
}

function releaseTable(b){
 return '<div class="table-wrap"><table><thead><tr><th>版本</th><th>研究批次 ID</th><th>记录数</th><th>内容指纹</th><th>确认人</th><th>确认时间</th><th>说明</th></tr></thead><tbody>'
 +b.releases.map(r=>'<tr><td>v'+r.revision+'</td><td><a class="text-link" href="#/workbench">#'+r.dataset_id+' 去分析 ↗</a></td><td>'+fmt(r.record_count)+'</td><td><small>'+esc(r.checksum.slice(0,24))+'…</small></td><td>'+esc(r.created_by)+'</td><td>'+esc(date(r.created_at))+'</td><td>'+esc(r.note||'—')+'</td></tr>').join('')
 +'</tbody></table></div>';
}

export function bindReconcile(refresh){
 const file=document.querySelector('#recon-file');
 if(file)file.addEventListener('change',async e=>{try{const f=e.target.files[0];if(!f)return;const text=await f.text(),records=f.name.endsWith('.csv')?parseCSV(text):JSON.parse(text);document.querySelector('[name=records]').value=JSON.stringify(records,null,2);}catch(err){notify(err.message,true);}});
 const form=document.querySelector('#recon-form');
 if(form)submit(form,async f=>{const r=await recon.upload({batch_key:f.get('batch_key'),source:f.get('source'),source_ref:file&&file.files[0]?file.files[0].name:'',records:JSON.parse(f.get('records'))});notify(r.idempotent?'同一来源内容一致，已幂等忽略':(r.reopened?'批次已重开，旧研究批次与任务固定':'来源已入账并完成核对'));location.hash='#/reconcile/'+r.id;await refresh();});
 document.querySelectorAll('[data-batch]').forEach(btn=>btn.onclick=()=>{location.hash='#/reconcile/'+btn.dataset.batch;});
 document.querySelectorAll('[data-resolve]').forEach(btn=>btn.onclick=async()=>{try{const b=workspace.reconSelected;await recon.resolve(b.id,[{id:Number(btn.dataset.resolve),adopt:btn.dataset.adopt,...(btn.dataset.seq!=null?{seq:Number(btn.dataset.seq)}:{})}]);notify('已记录采用来源');await refresh();}catch(err){notify(err.message,true);}});
 const all=document.querySelector('#resolve-all');
 if(all)all.onclick=async()=>{try{const b=workspace.reconSelected;await recon.resolve(b.id,[]);notify('已一次性采用全部挂起差异，可提交负责人确认');await refresh();}catch(err){notify(err.message,true);}};
 const confirmBtn=document.querySelector('#confirm-batch');
 if(confirmBtn)confirmBtn.onclick=async()=>{try{const b=workspace.reconSelected;const r=await recon.confirm(b.id,document.querySelector('#confirm-note').value);notify(r.new_dataset?'已切换为研究批次 v'+r.dataset_revision:'内容未变化，复用既有研究批次');location.hash='#/reconcile/'+b.id;await refresh();}catch(err){notify(err.message,true);}};
}
