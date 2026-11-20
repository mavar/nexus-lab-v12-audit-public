"""Targets from the best delayed exit. Features, fitted models and execution are separate."""
import numpy as np
from numba import njit

from harness_timed import GAP_MS, DELAY_MS

LAGS=(5,15,60)


def features(t,bid,ask):
    secs=[]; blocks=[]
    cuts=np.r_[0,np.flatnonzero(np.diff(t)>GAP_MS)+1,len(t)]
    for a,b in zip(cuts,cuts[1:]):
        clock=np.arange(-(-int(t[a])//1000)*1000,int(t[b-1])+1,1000,dtype=np.int64)
        if len(clock)<=60:continue
        k=a+np.searchsorted(t[a:b],clock,side='right')-1
        mid=(bid[k]+ask[k])/2
        ret=np.diff(np.log(mid),prepend=np.log(mid[0])); cumul=np.r_[0.,np.cumsum(ret*ret)]
        v=np.column_stack([*(mid[60:]/mid[60-lag:-lag]-1 for lag in LAGS),np.sqrt(np.maximum(0,(cumul[61:]-cumul[41:-20])/20)),(ask[k[60:]]-bid[k[60:]])/mid[60:]])
        secs.append(clock[60:]);blocks.append(v)
    return (np.concatenate(secs),np.concatenate(blocks)) if secs else (np.empty(0,dtype=np.int64),np.empty((0,5)))


@njit(cache=True)
def bound(t,x):
    l=0; r=len(t)
    while l<r:
        m=(l+r)//2
        if t[m]<x:l=m+1
        else:r=m
    return l


@njit(cache=True)
def first_below(low,start,end,cut,size):
    a=start+size;b=end+size;node=-1
    while a<=b:
        if a%2:
            if low[a]<cut:
                node=a;break
            a+=1
        if not b%2:
            if low[b]<cut:node=b
            b-=1
        a//=2;b//=2
    if node<0:return -1
    while node<size:
        node*=2
        if low[node]>=cut:node+=1
    return node-size


@njit(cache=True)
def prepare(t,bid):
    n=len(t);size=1
    while size<n:size*=2
    low=np.full(2*size,np.inf);high=np.full(2*size,-np.inf);sales=np.empty(n,np.int32);segment=np.empty(n,np.int32)
    p=0
    for i in range(n):
        while p<n and t[p]<t[i]+DELAY_MS:p+=1
        sales[i]=p;low[size+i]=bid[i]
        if p<n:high[size+i]=bid[p]
    segment[n-1]=n-1
    for i in range(n-2,-1,-1):segment[i]=i if t[i+1]-t[i]>GAP_MS else segment[i+1]
    for i in range(size-1,0,-1):low[i]=min(low[2*i],low[2*i+1]);high[i]=max(high[2*i],high[2*i+1])
    return low,high,sales,segment,size


@njit(cache=True)
def labeled_returns(t,bid,ask,clock,end,horizon,dip,fee,prepared,side=1):
    """For shorts prepare the tree with -ask, so a larger value is still favorable."""
    low,high,sales,segment,size=prepared; n=len(t); out=np.full(len(clock),np.nan);factor=(1.-fee)/(1.+fee)
    for i in range(len(clock)):
        d=clock[i];k=bound(t,d+1)-1;e=bound(t,d+DELAY_MS)
        if k<0 or t[k]<d-GAP_MS or e>=n or e>segment[k] or t[e]-d-DELAY_MS>GAP_MS:continue
        cap=min(end-1,t[e]+horizon); coverage=segment[k]; last=min(coverage,bound(t,cap+1)-1)
        threshold = bid[e]*(1.-dip) if side==1 else -ask[e]*(1.+dip)
        breach=first_below(low,e+1,last,threshold,size)
        if t[coverage]<cap and breach<0 and not (cap==end-1 and cap-t[coverage]<=GAP_MS):continue
        if breach>=0:last=breach-1
        if last<=e:
            if breach>=0:out[i]=-1.
            continue
        l=e+1;r=last+1
        while l<r:
            m=(l+r)//2
            if sales[m]<=last:l=m+1
            else:r=m
        a=e+1+size;b=l-1+size;v=-np.inf
        while a<=b:
            if a%2:v=max(v,high[a]);a+=1
            if not b%2:v=max(v,high[b]);b-=1
            a//=2;b//=2
        if np.isfinite(v):
            if side==1:out[i]=v/ask[e]*factor-1.
            else:out[i]=(bid[e]*(1.-fee)+v*(1.+fee))/(bid[e]*(1.+fee))
        elif breach>=0:out[i]=-1.
    return out
