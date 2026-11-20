'use strict';
const assert=require('node:assert/strict');
const {makeDay,mergeSides,scores,parts,grid,FEE}=require('./engine');
const fixture=()=>{
  const ts=Array.from({length:400},(_,i)=>100*i+(i>200?4000:0));
  const bid=ts.map((t,i)=>100+Math.sin(i*.04)*1.4+Math.sin(i*.17)*.17),ask=bid.map(p=>p+.005);
  return {ts,bid,ask};
};
const q=fixture();let checks=0,found=0;
// Compare the trees to an independent linear walk on both executable price sides.
for(const side of [1,-1])for(const seconds of [1,5,8])for(const dip of [.0005,.01]){
  const map=new Map(makeDay(q,side)(seconds,dip,1000,43000,true).map(r=>[r[0],r]));
  for(let t=1000;t<43000;t+=1000){
    const {ts,bid,ask}=q,exit=side===1?bid:ask,entry=side===1?ask:bid;
    const k=ts.findLastIndex(v=>v<=t),e=ts.findIndex(v=>v>=t+300);let ref;
    if(e>=0&&k>=0&&t-ts[k]<=2000&&ts[e]-t-300<=2000){
      let stop=e;while(stop>k&&ts[stop]-ts[stop-1]<=2000)stop--;
      if(stop===k){
        const bound=Math.min(ts[e]+1000*seconds,42999);let last=e,complete=false;
        for(let j=e+1;j<ts.length&&ts[j]-ts[j-1]<=2000;j++){
          if(ts[j]>bound||(side===1?exit[j]<exit[e]*(1-dip):exit[j]>exit[e]*(1+dip))){complete=true;break}
          last=j;if(ts[j]===bound||bound===42999&&bound-ts[j]<=2000)complete=true;
        }
        if(complete)for(let j=e+1;j<=last;j++){
          const x=ts.findIndex(v=>v>=ts[j]+300);if(x<0||x>last)break;
          if(!ref||side*(exit[x]-ref.p)>0)ref={x,p:exit[x],e};
        }
      }
    }
    const got=map.get(t);assert.equal(Boolean(got),Boolean(ref),`${side}/${seconds}/${dip}/${t}`);
    if(ref){const a=entry[ref.e],b=ref.p,expected=side===1?b*(1-FEE)/(a*(1+FEE))-1:(a*(1-FEE)-b*(1+FEE))/(a*(1+FEE));assert.equal(got[1],q.ts[ref.x]);assert.ok(Math.abs(got[2]-expected)<1e-12);found++}
    checks++;
  }
}
assert.ok(found);
// Two directions at the same second may not both use the same capital.
const rows=mergeSides([[0,2100,.05,1],[3000,3300,.03,1]],[[0,900,.025,-1],[1000,1800,.03,-1]]);
const r=scores(rows,[0,4,5],true);assert.equal(r[0].count,3);assert.equal(r[0].picks[0][3],-1);assert.equal(r[1].count,1);
assert.ok(Math.abs(Math.exp(r[0].log)-1.025*1.03**2)<1e-12);
assert.equal(parts({a:86000000,b:87000000}).length,2);
assert.deepEqual(grid({goal:1.07,seconds:42,dip:.02}).times,[30,42]);
console.log(`PASS: ${checks} linear comparisons (${found} valid), shared-capital chain and grid boundaries`);
