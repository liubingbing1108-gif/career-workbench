/** Execution protocol v1. Type declarations only; no profile or model dependency. */
export type Value = string | string[] | boolean;
export type Kind = 'text' | 'select' | 'autocomplete' | 'multiselect' | 'radio' | 'date' | 'month' | 'year' | 'checkbox' | 'unsupported';
export interface Fault { code: string; message: string; details?: unknown }
export type Reply<T> = {ok:true; result:T} | {ok:false; error:Fault};
export interface Page {adapter:string; url:string; title:string; section?:string}
export interface Field {
 fieldId:string; label:string; kind:Kind; sectionId:string; recordId:string;
 required:boolean; disabled:boolean; description:string; blockedReason:string;
 context:{section?:string; componentIndex?:number; placeholder?:string; tag?:string; type?:string; driver?:string};
 constraints:{maxLength?:number; format?:string};
 options:{state:'requires-opening'|'not-applicable'|'not-enumerated'|'enumerated'|'visible-options'; items:string[]; complete?:boolean};
 currentValue:Value;
}
export interface Section {sectionId:string; label:string; count?:number; canAdd:boolean}
export interface Snapshot {
 schemaVersion:1; executorVersion:string; sessionId:string; snapshotId:string; page:Page;
 capabilities:{fill:boolean; ensureRecords:boolean; openSection:boolean; saveDraft:boolean; upload:boolean; submit:false};
 attachments:{attachmentId:string;label:string;required:boolean;fileNames:string[]}[];
 scanElapsedMs:number; coverageDetails:{frames?:number;openShadowRoots?:number;frameContentsScanned?:boolean};
 sections:Section[]; fields:Field[]; coverage:'currently-accessible-fields'; validation:string[];
}
export interface Assignment {fieldId:string; value:Value; overwrite?:'emptyOnly'|'ifUnchanged'; sourceRef?:string}
export interface Plan {schemaVersion:1; requestId:string; snapshotId:string; assignments:Assignment[]}
export interface RecordPlan {schemaVersion:1; requestId:string; snapshotId:string; sections:{sectionId:string; count:number}[]}
export interface SavePlan {schemaVersion:1; requestId:string; snapshotId:string}
export interface AttachmentPlan extends SavePlan {attachmentId:string;fileName:string;mimeType:string;base64:string;sourceRef?:string}
export type Status = 'running'|'complete'|'failed'|'cancelled';
export interface Accepted {accepted:true; requestId:string; status:Status; replayed?:true}
export interface FieldResult {fieldId:string; label:string; sourceRef?:string; status:'filled'|'unchanged'; expected:Value; actual:Value; elapsedMs:number}
export interface RecordResult {sectionId:string; before:number; after:number; added:number}
export interface Job {
 requestId:string; method:'execute'|'ensureRecords'|'saveDraft'|'uploadAttachment'; page:Page; status:Status;
 elapsedMs:number; preflightMs:number; totalMs?:number; results:(FieldResult|RecordResult|{status:'website-save-success-feedback'}|{status:'attachment-uploaded'|'attachment-present';fileName:string})[];
 preserved?:number; submitted:false; saved:boolean; scope:'current-page';
 validation?:string[]; snapshot?:Snapshot; error?:Fault;
 currentField?:{label:string;index:number;total:number;sectionId:string}; progress?:string;
}
export interface Methods {
 scan:{input:Record<string,never>; output:Snapshot};
 readOptions:{input:{snapshotId:string;fieldId:string};output:Field['options']};
 readDateFormat:{input:{snapshotId:string;fieldId:string};output:{kind:'date'|'month';format:'YYYY-MM-DD'|'YYYY-MM';writesPerformed:0}};
 validate:{input:Plan; output:{valid:true; count:number; writesPerformed:0}};
 execute:{input:Plan; output:Accepted};
 ensureRecords:{input:RecordPlan; output:Accepted};
 status:{input:{requestId?:string}; output:Job|null};
 verify:{input:{requestId:string}; output:{complete:boolean; checks:{fieldId:string; passed:boolean}[]; validation:string[]; scope:'page-values-only'}};
 cancel:{input:Record<string,never>; output:{stopping:boolean}};
 openSection:{input:{sectionId:string}; output:Snapshot};
 saveDraft:{input:SavePlan; output:Accepted};
 uploadAttachment:{input:AttachmentPlan; output:Accepted};
}
/** Loaded by client.js inside the extension. No transport from ordinary webpages exists. */
export interface Client {call<M extends keyof Methods>(method:M, payload:Methods[M]['input']):Promise<Reply<Methods[M]['output']>>}
export type Request = {[M in keyof Methods]:{method:M; payload:Methods[M]['input']}}[keyof Methods];
