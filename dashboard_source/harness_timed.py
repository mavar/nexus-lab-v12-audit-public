"""Causal long-only historical execution in milliseconds; isolated from legacy tick mode."""
from collections import deque
from dataclasses import dataclass

import numpy as np
from numba import njit

DAY_MS, GAP_MS, DELAY_MS = 86_400_000, 2_000, 300


def signals(ts, bid, ask, day_start, rule, lookback=10, threshold=.0005, fast=8, slow=32):
    """Emit signals from the last quote known at each whole second; reset on feed gaps."""
    emitted = []
    cuts = np.r_[0, np.flatnonzero(np.diff(ts) > GAP_MS) + 1, len(ts)]
    for a, b in zip(cuts, cuts[1:]):
        seconds = np.arange(-(-int(ts[a])//1000)*1000, int(ts[b-1])+1, 1000, dtype=np.int64)
        if not len(seconds):
            continue
        ix = np.searchsorted(ts[a:b], seconds, side='right')-1+a
        mid = (bid[ix]+ask[ix])/2
        if rule == 'momentum_10s' and len(mid) > lookback:
            up = mid[lookback:] / mid[:-lookback] - 1 > threshold
            emitted.extend(seconds[lookback:][up & ~np.r_[False, up[:-1]]])
        elif rule == 'ema_cross':
            f = s = mid[0]
            for i in range(1, len(mid)):
                above = f > s
                f += 2/(fast+1)*(mid[i]-f); s += 2/(slow+1)*(mid[i]-s)
                if i >= slow and not above and f > s:
                    emitted.append(seconds[i])
        elif rule == 'prior_range_break':
            high = deque()
            for i, m in enumerate(mid):
                while high and high[0] < i-lookback:
                    high.popleft()
                if i >= lookback and m > mid[high[0]]*(1+threshold):
                    emitted.append(seconds[i])
                while high and mid[high[-1]] <= m:
                    high.pop()
                high.append(i)
    return np.asarray(emitted, dtype=np.int64)


@dataclass(frozen=True)
class TimedExit:
    take: float
    stop: float
    wait_ms: int
    fee: float
    delay_ms: int = DELAY_MS
    adverse: float | None = None


def execute_long_day(ts, bid, ask, signal_times, day_end, terms):
    """One position. A gap exit uses a later real bid, never a quote inside the gap.

    A missing end fill leaves an unresolved position. Caller must stop instead of
    reporting a made-up final balance. Seconds before midnight are known ex ante.
    """
    close_at = day_end-1000
    f, delay = terms.fee, terms.delay_ms
    factor = (1-f)/(1+f)
    cuts = np.r_[np.flatnonzero(np.diff(ts)>GAP_MS), len(ts)-1]
    trades, skip, i = [], 0, 0
    while i < len(signal_times):
        decision = int(signal_times[i]); i += 1
        if decision+delay >= close_at:
            break
        k = int(np.searchsorted(ts, decision, side='right')-1)
        e = int(np.searchsorted(ts, decision+delay))
        if k < 0 or decision-ts[k] > GAP_MS or e >= len(ts) or ts[e] >= close_at or np.any(np.diff(ts[k:e+1])>GAP_MS) or ts[e]-decision-delay>GAP_MS:
            skip += 1
            continue
        entry_t, entry = int(ts[e]), float(ask[e]); boundary = int(cuts[np.searchsorted(cuts, e)])
        deadline = min(entry_t+terms.wait_ms, close_at)
        gap_alarm = int(ts[boundary])+GAP_MS
        command, reason = (gap_alarm,'gap') if gap_alarm < deadline else (deadline,'session' if deadline == close_at else 'time')
        stop_ix = min(boundary+1,int(np.searchsorted(ts,command,side='right')))
        net = bid[e:stop_ix] / entry * factor - 1
        adverse=(bid[e:stop_ix]<bid[e]*(1-terms.adverse)) if terms.adverse is not None else np.zeros(len(net),dtype=bool)
        hits = np.flatnonzero((net>=terms.take)|(net<=-terms.stop)|adverse)
        if len(hits):
            h = int(hits[0]); command = int(ts[e+h]); reason = 'stop' if net[h]<=-terms.stop else 'dip' if adverse[h] else 'target'
        x = int(np.searchsorted(ts,command+delay))
        if x >= len(ts) or ts[x] >= day_end:
            return trades, {'entryTime':entry_t,'entryPrice':entry,'reason':'no_close_quote','decisionTime':decision}, skip
        # A gap after the close command is reflected in execution, even for a target hit.
        exit_t, exit_price = int(ts[x]), float(bid[x]); ret = exit_price / entry * factor - 1
        trades.append(dict(decisionTime=decision,entryTime=entry_t,exitCommandTime=command,exitTime=exit_t,entryPrice=entry,exitPrice=exit_price,netRate=ret,reason=reason,gapExposed=bool(x>boundary)))
        i = max(i,int(np.searchsorted(signal_times,exit_t,side='right')))
    return trades, None, skip


@njit(cache=True)
def prepare_entries(ts, clock, day_end, delay):
    """Map decisions to fills and continuous sections once per validation day."""
    boundaries = np.empty(len(ts), np.int32)
    boundary = len(ts) - 1
    for i in range(len(ts) - 1, -1, -1):
        if i < len(ts) - 1 and ts[i+1] - ts[i] > GAP_MS:
            boundary = i
        boundaries[i] = boundary
    entries = np.full(len(clock), -1, np.int32)
    for i, decision in enumerate(clock):
        if decision + delay >= day_end - 1000:
            break
        known = np.searchsorted(ts, decision, side='right') - 1
        entry = np.searchsorted(ts, decision + delay)
        if (known >= 0 and decision - ts[known] <= GAP_MS and entry <= boundaries[known]
                and ts[entry] < day_end - 1000 and ts[entry] - decision - delay <= GAP_MS):
            entries[i] = entry
    return entries, boundaries


@njit(cache=True)
def _net(side, entry, exit_price, fee, factor):
    if side == 1:
        return exit_price / entry * factor - 1
    return (entry * (1 - fee) - exit_price * (1 + fee)) / (entry * (1 + fee))


@njit(cache=True)
def _directional_fills(ts, bid, ask, clock, sides, entries, boundaries, day_end, take, stop, wait, fee, delay, dip):
    factor = (1-fee)/(1+fee)
    close_at = day_end - 1000
    fills = []
    blocked_until = -1
    skipped = 0
    for i in np.flatnonzero(sides):
        decision = clock[i]
        if decision <= blocked_until:
            continue
        if decision + delay >= close_at:
            break
        e = entries[i]
        if e < 0:
            skipped += 1
            continue
        side = sides[i]
        entry = ask[e] if side == 1 else bid[e]
        path = bid if side == 1 else ask
        boundary = boundaries[e]
        deadline = min(ts[e] + wait, close_at)
        command = min(deadline, ts[boundary] + GAP_MS)
        reason = 4 if command < deadline else (5 if deadline == close_at else 3)
        adverse_price = path[e] * (1 - side*dip)
        for j in range(e, boundary + 1):
            if ts[j] > command:
                break
            net = _net(side, entry, path[j], fee, factor)
            adverse = path[j] < adverse_price if side == 1 else path[j] > adverse_price
            if net >= take or net <= -stop or adverse:
                command = ts[j]
                reason = 1 if net <= -stop else (2 if adverse else 0)
                break
        x = np.searchsorted(ts, command + delay)
        if x >= len(ts) or ts[x] >= day_end:
            return fills, (i, e), skipped
        fills.append((i, e, x, command, reason, _net(side, entry, path[x], fee, factor), x > boundary))
        blocked_until = ts[x]
    return fills, (-1, -1), skipped


def execute_directional_day(ts, bid, ask, clock, sides, day_end, terms, prepared, details=True):
    fills, unresolved, skipped = _directional_fills(
        ts, bid, ask, clock, sides, *prepared, day_end,
        terms.take, terms.stop, terms.wait_ms, terms.fee, terms.delay_ms,
        np.inf if terms.adverse is None else terms.adverse,
    )
    if not details:
        return (fill[5] for fill in fills), unresolved[0] >= 0, skipped
    reasons = ('target', 'stop', 'dip', 'time', 'gap', 'session')
    trades = []
    for i, e, x, command, reason, net, gap in fills:
        long = sides[i] == 1
        trades.append(dict(side='long' if long else 'short', decisionTime=int(clock[i]), entryTime=int(ts[e]),
                           exitCommandTime=command, exitTime=int(ts[x]), entryPrice=float(ask[e] if long else bid[e]),
                           exitPrice=float(bid[x] if long else ask[x]), netRate=net, reason=reasons[reason], gapExposed=gap))
    opened = None
    i, e = unresolved
    if i >= 0:
        long = sides[i] == 1
        opened = dict(side='long' if long else 'short', decisionTime=int(clock[i]), entryTime=int(ts[e]),
                      entryPrice=float(ask[e] if long else bid[e]), reason='no_close_quote')
    return trades, opened, skipped
