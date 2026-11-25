const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
let handler, options, body, timeout;
const upstream = {setTimeout(ms){timeout=ms;},on(){},end(value){body=value;},destroy(){}};
const router = {use(prefix, parser, callback){assert.equal(prefix,'/exam_api/tutor');handler=callback;}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'common/bin/practice_tutor/editor_route.js'),'utf8'),
  {exports:{router},express:{json:()=>()=>{}},Buffer,require:name=>{assert.equal(name,'http');return {request(value){options=value;return upstream;}};}});
handler({method:'POST',url:'/messages',body:{message:'help'},headers:{'x-tutor-token':'csrf','authorization':'never-forward'},on(){}},{});
assert.equal(options.hostname,'127.0.0.1');assert.equal(options.port,5001);
assert.equal(options.path,'/exam_api/tutor/messages');assert.equal(options.headers['X-Tutor-Token'],'csrf');
assert.equal(options.headers.authorization,undefined);assert.equal(JSON.parse(body).message,'help');assert.equal(timeout,90000);
console.log('MUD same-origin route forwarding passed');
