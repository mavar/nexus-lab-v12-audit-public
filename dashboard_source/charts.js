// Step prices, gap shading, and exact entry/exit marker coordinates.
function chart(canvas,range,series,gaps,marks,focus,corridor){
  const w=canvas.clientWidth,h=canvas.clientHeight;if(w<120||h<70)return;
  const scale=window.devicePixelRatio||1;canvas.width=w*scale;canvas.height=h*scale;
  const g=canvas.getContext('2d');g.setTransform(scale,0,0,scale,0,0);
  const L=72,R=w-14,T=13,B=h-26,span=range.b-range.a;
  const x=t=>L+(t-range.a)/span*(R-L);let lo=Infinity,hi=-Infinity;
  for(const set of series)for(const r of set)if(r[0]>=range.a&&r[0]<=range.b){lo=Math.min(lo,r[1]);hi=Math.max(hi,r[2])}
  if(focus)for(const [t,p] of [[focus[4],focus[5]],[focus[1],focus[6]]])if(t>=range.a&&t<=range.b){lo=Math.min(lo,p);hi=Math.max(hi,p)}
  if(!Number.isFinite(lo)){g.fillStyle='#59697c';g.fillText('На этом участке нет котировок.',L,26);return}
  const pad=(hi-lo||hi*.002||.001)*.06;lo-=pad;hi+=pad;const y=p=>B-(p-lo)/(hi-lo)*(B-T);
  g.font='11px system-ui';g.fillStyle='#53657a';g.strokeStyle='#e6ebf2';g.lineWidth=1;
  for(let j=0;j<=5;j++){const a=T+j*(B-T)/5;g.beginPath();g.moveTo(L,a);g.lineTo(R,a);g.stroke();g.fillText((hi-j*(hi-lo)/5).toFixed(4),5,a+4)}
  const tick=span>=DAY?DAY:span>2*3600000?3600000:span>1200e3?600000:span>180000?60000:span>30000?15000:5000;
  for(let t=Math.ceil(range.a/tick)*tick;t<=range.b;t+=tick){const a=x(t);g.beginPath();g.moveTo(a,T);g.lineTo(a,B);g.stroke();g.fillText(tick===DAY?(DATA.days[Math.floor(t/DAY)]?.date.slice(5)||''):utc(t).slice(0,tick<60000?8:5),a-16,B+15)}
  g.save();g.beginPath();g.rect(L,T,R-L,B-T);g.clip();
  if(corridor){g.fillStyle='#e0edff';g.fillRect(x(corridor.a),T,x(corridor.b)-x(corridor.a),B-T)}
  for(const [a,b] of gaps){if(b<range.a||a>range.b)continue;g.fillStyle='#f8d87d60';g.fillRect(x(a),T,Math.max(1,x(b)-x(a)),B-T)}
  for(const [col,color] of [[1,'#265eab'],[2,'#ba7b54']]){
    g.strokeStyle=color;g.lineWidth=.9;
    for(const set of series){g.beginPath();let prior=null;for(const r of set){const t=r[0],z=y(r[col]);if(prior&&t<=range.b&&!gaps.some(([a,b])=>a>=prior[0]&&b<=t)){g.lineTo(x(t),prior[1]);g.lineTo(x(t),z)}else g.moveTo(x(t),z);prior=[t,z]}g.stroke()}
  }
  const drawn=new Set();
  function marker(t,p,side,exit,selected=false){if(t<range.a||t>range.b)return;const a=x(t),b=y(p),key=`${a|0},${b|0},${side},${exit}`;if(!selected&&drawn.has(key))return;drawn.add(key);
    const r=selected?6:3;g.fillStyle=g.strokeStyle=exit?'#713fa2':side===1?'#07804f':'#c13b43';g.lineWidth=selected?2:1;g.beginPath();
    if(exit){g.moveTo(a-r,b-r);g.lineTo(a+r,b+r);g.moveTo(a-r,b+r);g.lineTo(a+r,b-r);g.stroke()}
    else{g.moveTo(a,b-r*side);g.lineTo(a-r,b+r*side);g.lineTo(a+r,b+r*side);g.fill()}}
  for(const r of marks){marker(r[4],r[5],r[3],false);marker(r[1],r[6],r[3],true)}
  if(focus){g.setLineDash([4,4]);g.strokeStyle='#5b6c81';for(const t of [focus[0],focus[4],focus[7],focus[1]]){g.beginPath();g.moveTo(x(t),T);g.lineTo(x(t),B);g.stroke()}g.setLineDash([]);marker(focus[4],focus[5],focus[3],false,true);marker(focus[1],focus[6],focus[3],true,true)}
  g.restore();
}
