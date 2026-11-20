// Static Node VM checks for import JSON Code nodes; NOT a real n8n execution.
const fs=require('fs'); const vm=require('vm'); const assert=require('assert');
const path=require('path'); const root=path.join(__dirname,'..');
const main=JSON.parse(fs.readFileSync(path.join(root,'n8n/EUCERIN_Vercel_EndToEnd.json'),'utf8'));
const err=JSON.parse(fs.readFileSync(path.join(root,'n8n/EUCERIN_Vercel_Error_Handler.json'),'utf8'));
function jsNode(nodes,name,items){
 const n=nodes.find(n=>n.name===name);assert(n);
 const context={$input:{first:()=>items[0],all:()=>items},console};
 return vm.runInNewContext('(()=>{'+n.parameters.jsCode+'})()',context,{timeout:2500});
}
const files=['FactOccurrenceForecast_PowerBI.csv','DimSKU_Behavior.csv','DimDate_Extended_For_Forecast.csv'];
const expanded=jsNode(main.nodes,'09 | List pending CSV exports',[{json:{run_id:'run123',files_pending:files}}]);
assert.equal(expanded.length,3);assert.equal(expanded[0].json.file_name,files[0]);
assert.equal(expanded[1].pairedItem.item,0);
const confirmed=jsNode(main.nodes,'13 | Check all upload responses',files.map(f=>({json:{run_id:'run123',file_name:f,acknowledged:true}})));
assert.equal(confirmed[0].json.run_id,'run123');
assert.throws(()=>jsNode(main.nodes,'13 | Check all upload responses',[{json:{run_id:'a',acknowledged:false}}]));
const metadata=jsNode(main.nodes,'03A | Validate source metadata',[{json:{id:'drive-source',modifiedTime:'2026-11-19T00:00:00Z',mimeType:'text/csv'}}]);
assert.equal(metadata[0].json.revision,'2026-11-19T00:00:00Z');
assert.throws(()=>jsNode(main.nodes,'03A | Validate source metadata',[{json:{id:'sheet',modifiedTime:'rev',mimeType:'application/vnd.google-apps.spreadsheet'}}]));
const config=main.nodes.find(n=>n.name==='02 | Config - Vercel, Drive, Telegram');
const configured=main.nodes.map(n=>n.name===config.name?{...n,parameters:{...n.parameters,jsCode:n.parameters.jsCode
 .replace('REPLACE_WITH_SOURCE_CSV_FILE_ID','drive-source')
 .replace('REPLACE_WITH_OUTPUT_FOLDER_ID','drive-output')
 .replace('REPLACE_WITH_TELEGRAM_CHAT_ID','chat-123')}}:n);
const conf=jsNode(configured,config.name,[]);
assert.equal(conf[0].json.apiBaseUrl,'https://eucerin-ml-automation.vercel.app');
assert.equal(conf[0].json.sourceFileId,'drive-source');
const alert=jsNode(err.nodes,'E2 | Sanitize error message',[{json:{workflow:{name:'Eucerin'},execution:{lastNodeExecuted:'Drive node',id:'test-3',error:{message:'SECURITY_KEY_LEAK?'}}}}]);
assert.equal(alert.length,1);assert(!alert[0].json.text.includes('SECURITY_KEY_LEAK?'));
console.log('PASS n8n Vercel Code nodes: config, source metadata, CSV tasks, acknowledgement, sanitized error alert');
