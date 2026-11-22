const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const path=require('node:path');
for (const file of ['common/web/js/exam-badge.js', 'exam_common/web/js/exam-badge.js']) {
const source=fs.readFileSync(path.join(__dirname,file),'utf8');
const helper=source.slice(0,source.indexOf('// Practice controls use'));
let frameId=0,restored=0,resizeObserver,visibilityObserver;
const frames=new Map(),windowEvents={},documentEvents={};
const dimensions={width:0,height:0};
const root={getBoundingClientRect:()=>({...dimensions})};
const document={hidden:false,documentElement:root,addEventListener:(name,fn)=>{documentEvents[name]=fn;}};
const context=vm.createContext({document,
 window:{addEventListener:(name,fn)=>{windowEvents[name]=fn;}},
 requestAnimationFrame:fn=>{frames.set(++frameId,fn);return frameId;},cancelAnimationFrame:id=>frames.delete(id),
 ResizeObserver:class{constructor(fn){resizeObserver=fn;}observe(node){assert.equal(node,root);}},
 IntersectionObserver:class{constructor(fn){visibilityObserver=fn;}observe(node){assert.equal(node,root);}}
});
vm.runInContext(helper,context);
context.observePracticeToolbarLayout(()=>{restored++;});
const tick=()=>{const ready=[...frames.values()];frames.clear();ready.forEach(fn=>fn());};
const settle=()=>{tick();tick();};
settle();assert.equal(restored,0,'collapsed frame must not apply clamped positions');
dimensions.width=1340;dimensions.height=800;
visibilityObserver([{isIntersecting:true}]);tick();assert.equal(restored,0,'wait through first layout frame');tick();assert.equal(restored,1);
resizeObserver([{contentRect:{width:1340,height:800}}]);settle();
const afterResize=restored;
resizeObserver([{contentRect:{width:1340,height:800}}]);assert.equal(frames.size,0,'unchanged dimensions do not schedule work');
visibilityObserver([{isIntersecting:false}]);assert.equal(frames.size,0);
visibilityObserver([{isIntersecting:true}]);settle();assert.equal(restored,afterResize+1,'reopening panel works without a viewport resize');
for(let i=0;i<5;i++)windowEvents.resize();settle();assert.equal(restored,afterResize+2,'resize bursts coalesce');
document.hidden=true;documentEvents.visibilitychange();settle();assert.equal(restored,afterResize+2);
document.hidden=false;documentEvents.visibilitychange();settle();assert.equal(restored,afterResize+3);
assert.equal(frames.size,0);assert.ok(!helper.includes('setInterval'));
console.log('Passed: collapsed startup, opening/reopening without resize, two-frame delay, unchanged-size filtering, resize coalescing, and visibility changes; no polling timer.');

}
