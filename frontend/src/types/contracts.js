/** @typedef {{id:number,name:string,source:string,rows:number,checksum:string,origin:string,recon_batch_id:?number,revision:number}} Dataset */
/** @typedef {{id:number,name:string,dataset_id:number,status:string,result:Object,approved:boolean}} AnalysisJob */
/** @typedef {{id:number,name:string,job_id:number,destination:string,next_run:number,enabled:boolean}} ReportSchedule */
/** @typedef {{id:number,batch_key:string,status:string,revision:number,stats:Object,confirmed_at:?number,confirmed_by:?string}} ReconBatchInfo */
/** @typedef {{id:number,batch_id:number,kind:string,station:string,period:number,status:string,detail:Object,resolution:Object}} ReconDifferenceInfo */
/** @typedef {{id:number,batch_id:number,revision:number,dataset_id:number,record_count:number,checksum:string,created_at:number,created_by:string,note:string}} ReconReleaseInfo */
export {};
