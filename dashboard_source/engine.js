'use strict';
// Historical labeling only. Short is a cash-collateralized hypothetical trade.
const DAY=86400000, DELAY=300, GAP=2000, FEE=.0005;
const GOALS=[0,.025,.05,.075,.1,.15,.2,.25,.5,.75,1,1.5,2,2.5,3,3.5,4,4.5,5];
const DIPS=[0,.01,.02,.05,.1,.2,.35,.5,1];
const TIMES=[30,60,120,300,600,900,1800,3600,7200,14400,21600];
function lower(a,t){let l=0,r=a.length;while(l<r){const m=(l+r)>>>1;if(a[m]<t)l=m+1;else r=m}return l}
function makeDay(q,side){
  const {ts,bid,ask}=q,n=ts.length,exit=side===1?bid:ask,entry=side===1?ask:bid;let size=1;while(size<n)size*=2;
  const low=new Float64Array(2*size).fill(Infinity),best=new Int32Array(2*size).fill(-1),sale=new Int32Array(n),end=new Int32Array(n);
  function higher(a,b){if(a<0)return b;if(b<0)return a;const d=side*(exit[sale[a]]-exit[sale[b]]);return d>0?a:d<0?b:Math.min(a,b)}
  for(let j=0,x=0;j<n;j++){while(x<n&&ts[x]<ts[j]+DELAY)x++;sale[j]=x;low[size+j]=side*exit[j];if(x<n)best[size+j]=j}
  for(let j=size-1;j;j--){low[j]=Math.min(low[j*2],low[j*2+1]);best[j]=higher(best[j*2],best[j*2+1])}
  end[n-1]=n-1;for(let j=n-2;j>=0;j--)end[j]=ts[j+1]-ts[j]>GAP?j:end[j+1];
  function breach(a,b,stop,l=0,r=size-1,node=1){if(r<a||l>b||low[node]>=stop)return -1;if(l===r)return l;const m=(l+r)>>>1,x=breach(a,b,stop,l,m,node*2);return x<0?breach(a,b,stop,m+1,r,node*2+1):x}
  function query(a,b){let x=-1;for(a+=size,b+=size;a<=b;a>>=1,b>>=1){if(a&1)x=higher(x,best[a++]);if(!(b&1))x=higher(x,best[b--])}return x}
  function minimum(a,b){let x=Infinity;for(a+=size,b+=size;a<=b;a>>=1,b>>=1){if(a&1)x=Math.min(x,low[a++]);if(!(b&1))x=Math.min(x,low[b--])}return x}
  const k0=new Int32Array(86400),e0=new Int32Array(86400);for(let s=0,k=-1,e=0;s<86400;s++){const t=s*1000;while(k+1<n&&ts[k+1]<=t)k++;while(e<n&&ts[e]<t+DELAY)e++;k0[s]=k;e0[s]=e}
  let cachedDip,stops;
  function prepare(dip){if(cachedDip===dip)return;cachedDip=dip;stops=new Int32Array(86400).fill(-1);for(let s=0;s<86400;s++){const e=e0[s],k=k0[s];if(k>=0&&e<=end[k])stops[s]=breach(e+1,end[k],side===1?bid[e]*(1-dip):-(ask[e]*(1+dip)))}}
  return function labels(secs,dip,from,to,detail=false){
    prepare(dip);const rows=[], lastInScope=lower(ts,to)-1, horizon=secs*1000;
    for(let s=Math.ceil(from/1000),s1=Math.min(86400,Math.ceil(to/1000));s<s1;s++){
      const t=s*1000,k=k0[s],e=e0[s];if(k<0||t-ts[k]>GAP||e>Math.min(end[k],lastInScope)||ts[e]-t-DELAY>GAP)continue;
      const bound=ts[e]+horizon, cap=Math.min(bound,to-1), stop=stops[s];
      // A known breach can end an opportunity early; without it, a gap makes the rest unknown.
      const coverage=end[k];if(ts[coverage]<cap&&!(stop>=0&&ts[stop]<=cap)&&!(cap===to-1&&cap-ts[coverage]<=GAP))continue;
      const last=Math.min(lastInScope,coverage,lower(ts,cap+1)-1,stop<0?n-1:stop-1);
      if(last<=e)continue;let l=e+1,r=last+1;while(l<r){const m=(l+r)>>>1;if(sale[m]<=last)l=m+1;else r=m}
      const j=query(e+1,l-1);if(j<0)continue;const x=sale[j],p=entry[e],z=exit[x];
      const net=side===1?z*(1-FEE)/(p*(1+FEE))-1:(p*(1-FEE)-z*(1+FEE))/(p*(1+FEE));
      if(detail)rows.push([t,ts[x],net,side,ts[e],p,z,ts[j],Math.max(0,(side*exit[e]-minimum(e,x))/exit[e])]);
      else if(net>0)rows.push([t,ts[x],net,side]);
    }
    return rows;
  };
}
function mergeSides(a,b){const out=[];for(let i=0,j=0;i<a.length||j<b.length;){out.push(j>=b.length||i<a.length&&a[i][0]<=b[j][0]?a[i++]:b[j++])}return out}
function scores(rows,goals,includePicks=false){
  const n=rows.length,starts=rows.map(r=>r[0]),next=new Int32Array(n),weights=new Float64Array(n);
  for(let j=0;j<n;j++){next[j]=Math.max(j+1,lower(starts,rows[j][1]));weights[j]=Math.log1p(Math.max(0,rows[j][2]))}
  const dp=new Float64Array(n+1),count=new Int32Array(n+1),pick=includePicks?new Uint8Array(n):null;
  return goals.map(goal=>{const g=goal/100;let possible=0;
    for(let j=n-1;j>=0;j--){const r=rows[j],ok=r[2]>0&&r[2]>=g,s=ok?weights[j]+dp[next[j]]:-Infinity, take=s>dp[j+1]+1e-15;if(ok)possible++;dp[j]=take?s:dp[j+1];count[j]=take?1+count[next[j]]:count[j+1];if(pick)pick[j]=take?1:0}
    const result={log:dp[0],count:count[0],possible};if(pick){result.picks=[];for(let j=0;j<n;){if(pick[j]){result.picks.push(rows[j]);j=next[j]}else j++}}return result;
  });
}
function grid(limit){const clipped=(a,v)=>[...new Set([...a.filter(x=>x<=v),v])].sort((a,b)=>a-b);return {times:clipped(TIMES,limit.seconds),dips:clipped(DIPS,limit.dip),goals:[...new Set([limit.goal,...GOALS.filter(x=>x>=limit.goal)])]}}
async function unpack(day){
  const bytes=Uint8Array.from(atob(day.packed),c=>c.charCodeAt(0));
  const buf=await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
  const n=day.n,k=day.changes, ts=new Uint32Array(buf,0,n),view=new DataView(buf),ct=new Uint32Array(buf,n*4+16*k,k);
  if(buf.byteLength!==n*4+20*k)throw Error('Упаковка котировок повреждена.');
  for(let i=1;i<n;i++)ts[i]+=ts[i-1];
  if(ts[n-1]!==ct[k-1])throw Error('Не совпадает время последней котировки.');
  const cb=new Float64Array(k),ca=new Float64Array(k),bid=new Float64Array(n),ask=new Float64Array(n);
  for(let i=0;i<k;i++){cb[i]=view.getFloat64(n*4+8*i,true);ca[i]=view.getFloat64(n*4+8*(k+i),true)}
  for(let i=0,j=0;i<n;i++){while(j+1<k&&ct[j+1]<=ts[i])j++;bid[i]=cb[j];ask[i]=ca[j]}
  return {ts,bid,ask,ct,cb,ca};
}
function parts(range){const out=[];for(let i=Math.floor(range.a/DAY);i<Math.ceil(range.b/DAY);i++)out.push({i,a:Math.max(0,range.a-i*DAY),b:Math.min(DAY,range.b-i*DAY)});return out}
function dayModes(q,mode){return {long:mode!=='short'?makeDay(q,1):null,short:mode!=='long'?makeDay(q,-1):null}}
function labelMode(engines,seconds,dip,a,b,detail){const l=engines.long?.(seconds,dip,a,b,detail),s=engines.short?.(seconds,dip,a,b,detail);return l&&s?mergeSides(l,s):l||s}
async function search(days,scope,mode,limit,onProgress,stopped=()=>false){
  const {times,dips,goals}=grid(limit),slices=parts(scope),rank=[];
  for(const dip of dips)for(const seconds of times)for(const goal of goals)rank.push({dip,seconds,goal,log:0,count:0,possible:0,daily:[]});
  let done=0,total=slices.length*dips.length*times.length;
  for(const {i,a,b} of slices){
    if(stopped())return null;
    const engines=dayModes(await unpack(days[i]),mode);let offset=0;
    for(const dip of dips)for(const seconds of times){
      if(stopped())return null;
      const labels=labelMode(engines,seconds,dip/100,a,b,false);
      for(const z of scores(labels,goals)){
        const r=rank[offset++];r.log+=z.log;r.count+=z.count;r.possible+=z.possible;r.daily.push({day:i,net:Math.expm1(z.log)*100,count:z.count});
      }
      onProgress(++done,total,i);
      await new Promise(r=>setTimeout(r,0));
    }
  }
  for(const r of rank)r.capital=100*Math.exp(r.log);
  return rank.sort((a,b)=>b.log-a.log||a.dip-b.dip||a.seconds-b.seconds||b.goal-a.goal);
}
if(typeof module!=='undefined')module.exports={makeDay,mergeSides,scores,grid,unpack,parts,dayModes,labelMode,search,DAY,DELAY,GAP,FEE};
