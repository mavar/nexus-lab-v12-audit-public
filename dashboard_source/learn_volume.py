"""Causal SOL trade activity and volume by price from the public spot tape."""
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from numba import njit
from dashboard_config import path_setting

TRADE_ROOT = path_setting('NEXUS_TRADE_ROOT','tradeRoot',r'G:\mexc_base\exchange=MEXC\stream=trades')
BUCKET_USDT = .05
TRADE_GAP_MS = 120_000


def trade_path(day):
    paths = list((TRADE_ROOT/'symbol=SOLUSDT'/f'date={day}').glob('*.parquet'))
    if len(paths) != 1:
        raise ValueError(f'Нужен один файл сделок SOLUSDT за {day}. Найдено: {len(paths)}.')
    return paths[0]


@lru_cache(maxsize=7)
def read_trades(day):
    table = pq.ParquetFile(trade_path(day)).read(columns=['recv_ts_ms','price','quantity','trade_time_ms'])
    t, price, qty, exchange = (column.to_numpy() for column in table.columns)
    if (not len(t) or not all(np.isfinite(a).all() for a in (t, price, qty, exchange))
            or np.any(price<=0) or np.any(qty<=0) or np.any(t<exchange)):
        raise ValueError(f'В файле сделок за {day} есть пустые или неверные строки.')
    order = np.argsort(t, kind='stable')
    return t[order], price[order], qty[order]


@njit(cache=True)
def rolling_volume(t, price, qty, clock, mid, recent_return, window_ms):
    """Each decision uses only trades received by that instant."""
    buckets = np.floor(price / BUCKET_USDT + 1e-9).astype(np.int64)
    offset = buckets.min()
    size = buckets.max() - offset + 1
    if size > 30_000:
        raise ValueError('Слишком широкий разброс цен в файле сделок SOLUSDT.')
    bins = np.zeros(size)
    out = np.full((len(clock), 10), np.nan)
    left = right = half = segment = 0
    total = newest = 0.
    for i, now in enumerate(clock):
        while right < len(t) and t[right] <= now:
            if right > 0 and t[right] - t[right-1] > TRADE_GAP_MS:
                bins[:] = 0
                left = half = segment = right
                total = newest = 0.
            bins[buckets[right]-offset] += qty[right]
            total += qty[right]
            newest += qty[right]
            right += 1
        while left < right and t[left] <= now - window_ms:
            bins[buckets[left]-offset] -= qty[left]
            total -= qty[left]
            left += 1
        while half < right and t[half] <= now - window_ms / 2:
            newest -= qty[half]
            half += 1
        if (right == 0 or now - t[segment] < window_ms or now - t[right-1] > TRADE_GAP_MS
                or right == left or total <= 0):
            continue
        strongest = np.argmax(bins)
        level = (strongest + offset + .5) * BUCKET_USDT
        previous = mid[i] / (1 + recent_return[i])
        out[i,0] = np.log1p(right-left)
        out[i,1] = np.log1p(total)
        out[i,2] = (right-half - (half-left))/(right-left)
        out[i,3] = bins[strongest]/total
        out[i,4] = level/mid[i] - 1
        out[i,5] = (abs(level-previous) - abs(level-mid[i]))/mid[i]
        split = int(np.ceil(mid[i] / BUCKET_USDT - .5)) - offset
        split = max(0, min(size, split))
        out[i,6:] = 0
        if split > 0:
            below = np.argmax(bins[:split])
            if bins[below] > 1e-9:
                out[i,6] = (below + offset + .5) * BUCKET_USDT / mid[i] - 1
                out[i,7] = bins[below] / total
        if split < size:
            above = split + np.argmax(bins[split:])
            if bins[above] > 1e-9:
                out[i,8] = (above + offset + .5) * BUCKET_USDT / mid[i] - 1
                out[i,9] = bins[above] / total
    return out


def add_volume(quotes, clock, x, trades, seconds):
    t, bid, ask = quotes
    idx = np.searchsorted(t, clock, side='right') - 1
    mid = (bid[idx] + ask[idx])/2
    extra = rolling_volume(*trades, clock, mid, x[:,0], seconds*1000)
    known = np.isfinite(extra).all(axis=1)
    return clock[known], np.column_stack((x[known], extra[known]))
