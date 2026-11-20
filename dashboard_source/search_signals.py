"""Research one shared spot entry filter for all three fitted models."""
import argparse
import json
from math import prod
from pathlib import Path
from random import Random
from time import perf_counter

import numpy as np
from threadpoolctl import threadpool_limits

from lab_api import DAY_MS, LearnInput, midnight, read_day
from learn_jobs import FIT, SELECT, entry_sides, evaluate, execution_quotes, model_for, validation_day, with_volume
from learn_labels import features, labeled_returns, prepare

SEED = 42
FEE_PCT = .05
STRESS_SLIP_PCT = .02
MIN_SEARCH_TRADES = 20
MIN_CHECK_TRADES = 10
MIN_GAIN_USDT = 1.
ENTRY_BUFFER_SECONDS = 600
MODELS = ('tree', 'logistic', 'bayes')
WINDOWS = (60, 120)
SCORE_THRESHOLDS = (10, 20, 30)
GATES = {
    'min_return_5s_pct': (None, -.04, 0., .01, .025, .05),
    'min_trade_count': (None, 10, 20, 40, 80),
    'min_trade_acceleration': (None, -.25, 0., .2, .4),
    'min_move_toward_level_pct': (None, 0., .01, .025),
    'min_strongest_level_share': (None, .15, .30, .50),
    'max_spread_pct': (None, .01, .02, .03),
}
AXES = (WINDOWS, SCORE_THRESHOLDS, *GATES.values())


def config(model, window, score_threshold=30):
    return LearnInput(model=model, complexity=3 if model == 'tree' else 1,
                      confidencePct=score_threshold, volumeSeconds=window, tradeFeePct=FEE_PCT)


def fit_models():
    training = {window: ([], []) for window in WINDOWS}
    cfg = config('tree', WINDOWS[0])
    for date in FIT:
        quotes = read_day(date)
        t, bid, ask = quotes
        clock, x = features(*quotes)
        clock, x = clock[::3], x[::3]
        raw = labeled_returns(t, bid, ask, clock, midnight(date) + DAY_MS,
                              cfg.holdSeconds*1000, cfg.dipPct/100, FEE_PCT/100, prepare(t,bid))
        for window, (features_list, labels_list) in training.items():
            available, expanded = with_volume(date, quotes, clock, x, window)
            returns = raw[np.searchsorted(clock, available)]
            known = np.isfinite(returns)
            features_list.append(expanded[known])
            labels_list.append(returns[known] >= cfg.targetPct/100)
    fitted = {}
    for window, (xs, ys) in training.items():
        x, y = np.concatenate(xs), np.concatenate(ys)
        fitted[window] = {model: model_for(config(model, window)).fit(x, y) for model in MODELS}
    return fitted


def prepare_period(dates, fitted):
    days = {window: [validation_day(date, window) for date in dates] for window in WINDOWS}
    probabilities = {
        window: {name: [model.predict_proba(day[3])[:, 1] for day in days[window]]
                 for name, model in fitted[window].items()}
        for window in WINDOWS
    }
    return days, probabilities


def dimensions(x):
    return (x[:, 0]*100, np.expm1(x[:, 5]), x[:, 7], x[:, 10]*100, x[:, 8], x[:, 4]*100)


def decode(genome):
    return tuple(axis[index] for index, axis in zip(genome, AXES, strict=True))


def mask_for(x, thresholds):
    mask = np.ones(len(x), dtype=bool)
    for i, (column, value) in enumerate(zip(dimensions(x), thresholds, strict=True)):
        if value is not None:
            mask &= column <= value if i == len(GATES)-1 else column >= value
    return mask


def assess(days, probabilities, genome, score_only=False, slip_pct=0.):
    window, score_threshold, *thresholds = decode(genome)
    period = days[window]
    masks = [mask_for(day[3], thresholds) for day in period]
    execution = period
    if slip_pct:
        execution = [(date, execution_quotes(quotes, slip_pct), clock, x, prepared)
                     for date, quotes, clock, x, prepared in period]
    results = {}
    for name in MODELS:
        cfg = config(name, window, score_threshold)
        entries = []
        for scores, mask, day in zip(probabilities[window][name], masks, period, strict=True):
            base = entry_sides({1: scores}, cfg.confidencePct/100)
            # Only score the recorded interval. Reserve time for exits before the file ends.
            last_entry = day[1][0][-1] - ENTRY_BUFFER_SECONDS*1000
            base[day[2] >= last_entry] = 0
            if score_only:
                # Keep the same number of candidate seconds, using only the model score.
                count = np.count_nonzero(base & mask)
                eligible = np.flatnonzero(base)
                chosen = eligible[np.argsort(-scores[eligible], kind='stable')[:count]]
                base[:] = 0
                base[chosen] = 1
                entries.append(base)
            else:
                entries.append(base * mask)
        balance, trades, drawdown, complete = evaluate(cfg, execution, entries, FEE_PCT)
        results[name] = dict(balance=balance, trades=trades, drawdown=drawdown, complete=complete)
    return results


def gains(result, baseline):
    return {name: result[name]['balance']-baseline[name]['balance'] for name in MODELS}


def eligible(result, minimum):
    return all(x['complete'] and x['trades'] >= minimum for x in result.values())


def evolve(score, population_size, rounds, seed):
    rng = Random(seed)
    cache = {}
    population = [tuple(rng.randrange(len(axis)) for axis in AXES)
                  for _ in range(population_size)]
    for _ in range(rounds):
        for candidate in population:
            if candidate not in cache:
                cache[candidate] = score(candidate)
        elite = sorted(set(population), key=lambda g: (cache[g], g), reverse=True)[:8]
        population = elite.copy()
        while len(population) < population_size:
            parent, other = rng.choice(elite), rng.choice(elite)
            child = [rng.choice(pair) for pair in zip(parent, other, strict=True)]
            for i, axis in enumerate(AXES):
                if rng.random() < .25:
                    child[i] = rng.randrange(len(axis))
            population.append(tuple(child))
        print(f'Проверено разных условий: {len(cache)}', flush=True)
    return cache


def run(population=32, rounds=10):
    started = perf_counter()
    with threadpool_limits(limits=1):
        fitted = fit_models()
        search_days, search_scores = prepare_period(SELECT[:2], fitted)
        def open_gate(window, threshold):
            return (window, threshold, *(0 for _ in GATES))

        baseline = {(w,s): assess(search_days, search_scores, open_gate(w,s))
                    for w in range(len(WINDOWS)) for s in range(len(SCORE_THRESHOLDS))}

        def score(candidate):
            result = assess(search_days, search_scores, candidate)
            matched = assess(search_days, search_scores, candidate, score_only=True)
            improve = gains(result, matched)
            enough = eligible(result, MIN_SEARCH_TRADES) and eligible(matched, MIN_SEARCH_TRADES)
            trades = min(x['trades'] for x in (*result.values(), *matched.values()))
            return enough, 0 if enough else trades, min(improve.values()), sum(improve.values())

        tried = evolve(score, population, rounds, SEED)
        usable = [candidate for candidate in tried if tried[candidate][0]]
        if not usable:
            return dict(seed=SEED, tested=len(tried), winner=None,
                        maximum_common_trade_count=max(score[1] for score in tried.values()),
                        seconds=perf_counter()-started)
        winner = max(usable, key=lambda g: (tried[g], g))
        window, score_threshold, *thresholds = decode(winner)
        search_result = assess(search_days, search_scores, winner)
        search_matched = assess(search_days, search_scores, winner, score_only=True)
        # Only the single already chosen candidate is run on the last day.
        check_days, check_scores = prepare_period(SELECT[2:], fitted)
        reference = open_gate(*winner[:2])
        check = assess(check_days, check_scores, winner)
        check_base = assess(check_days, check_scores, reference)
        check_gains = gains(check, check_base)
        stress = assess(check_days, check_scores, winner, slip_pct=STRESS_SLIP_PCT)
        stress_base = assess(check_days, check_scores, reference, slip_pct=STRESS_SLIP_PCT)
        matched = assess(check_days, check_scores, winner, score_only=True)
        stress_matched = assess(check_days, check_scores, winner, score_only=True, slip_pct=STRESS_SLIP_PCT)
        check_matched_gains = gains(check, matched)
        check_stress_gains = gains(stress, stress_matched)
        return dict(seed=SEED, tested=len(tried), possible=prod(map(len, AXES)),
                    fit_days=list(map(str,FIT)), search_days=list(map(str,SELECT[:2])),
                    check_days=list(map(str,SELECT[2:])), fee_pct=FEE_PCT, stress_slip_pct=STRESS_SLIP_PCT,
                    last_entry_buffer_seconds_before_last_recorded_quote=ENTRY_BUFFER_SECONDS,
                    minimum_gain_usdt=MIN_GAIN_USDT, minimum_search_trades=MIN_SEARCH_TRADES,
                    minimum_check_trades=MIN_CHECK_TRADES, config=config('tree',window,score_threshold).model_dump(),
                    winner=dict(window=window, **dict(zip(GATES, thresholds, strict=True))),
                    search=dict(result=search_result, baseline=baseline[winner[:2]], gain=gains(search_result, baseline[winner[:2]]),
                                matched_model_score_only=search_matched, gain_vs_matched=gains(search_result, search_matched)),
                    check=dict(result=check, baseline=check_base, gain=check_gains, matched_model_score_only=matched,
                               gain_vs_matched=check_matched_gains, stress=stress, stress_baseline=stress_base,
                               stress_matched_model_score_only=stress_matched, stress_gain_vs_matched=check_stress_gains),
                    screen_passed=(all(eligible(period, MIN_CHECK_TRADES) for period in (check, matched, stress, stress_matched))
                                   and min(tried[winner][2], min(check_matched_gains.values()))>=MIN_GAIN_USDT
                                   and min(check_stress_gains.values())>=0),
                    seconds=perf_counter()-started)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(run(), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
