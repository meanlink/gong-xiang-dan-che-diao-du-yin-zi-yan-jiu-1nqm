import {api} from './client.js';
export const datasets={list:()=>api('/datasets'),get:id=>api('/datasets/'+id),create:data=>api('/datasets',{method:'POST',body:JSON.stringify(data)})};
export const jobs={list:()=>api('/jobs'),get:id=>api('/jobs/'+id),create:data=>api('/jobs',{method:'POST',body:JSON.stringify(data)}),approve:id=>api('/jobs/'+id+'/approve',{method:'POST'})};
export const reports={list:()=>api('/reports'),create:data=>api('/reports',{method:'POST',body:JSON.stringify(data)}),toggle:id=>api('/reports/'+id+'/toggle',{method:'POST'}),deliveries:()=>api('/deliveries')};
export const recon={
 batches:()=>api('/recon/batches'),
 batch:id=>api('/recon/batches/'+id),
 upload:data=>api('/recon/sources',{method:'POST',body:JSON.stringify(data)}),
 resolve:(id,items)=>api('/recon/batches/'+id+'/resolve',{method:'POST',body:JSON.stringify({items})}),
 confirm:(id,note)=>api('/recon/batches/'+id+'/confirm',{method:'POST',body:JSON.stringify({note:note||''})})
};
