import unittest
import numpy as np
from lab_api import RunInput
from harness_timed import TimedExit, execute_long_day, signals
from harness_timed import execute_directional_day, prepare_entries


class TimedExecutionTest(unittest.TestCase):
    def test_each_signal_is_prefix_invariant(self):
        t=np.arange(25,250_000,100,dtype=np.int64);mid=70+np.sin(t/4370)*.4+t/900_000
        for rule in ('momentum_10s','ema_cross','prior_range_break'):
            times=signals(t,mid-.005,mid+.005,0,rule)
            self.assertGreater(len(times),0,rule)
            for cut in (600,1200,1800):
                result=signals(t[:cut],mid[:cut]-.005,mid[:cut]+.005,0,rule)
                np.testing.assert_array_equal(result,times[times<=t[cut-1]])

    def test_prices_commission_and_delay_are_real(self):
        t=np.array([0,1000,1280,1420,1580,1990,2510,4100]);b=np.array([99,99,99,99,102,101,100,100.]);a=b+1
        result, opened, skipped=execute_long_day(t,b,a,[1000],6000,TimedExit(.01,.03,120_000,.0005))
        self.assertIsNone(opened);self.assertEqual(skipped,0); self.assertEqual(len(result),1)
        z=result[0];self.assertEqual((z['entryTime'],z['exitCommandTime'],z['exitTime']),(1420,1580,1990))
        self.assertEqual(z['reason'],'target');self.assertAlmostEqual(z['netRate'],101*.9995/(100*1.0005)-1)

    def test_outage_closes_only_when_next_real_quote_arrives(self):
        t=np.array([0,1000,1400,1500,1600,5500,6050]);b=np.array([100,100,100,100,100,90,91.]);a=b+.01
        result, opened, _=execute_long_day(t,b,a,[1000],9000,TimedExit(.05,.02,40000,.0005))
        self.assertIsNone(opened);self.assertEqual(result[0]['reason'],'gap');self.assertTrue(result[0]['gapExposed']);self.assertEqual(result[0]['exitTime'],5500)
        self.assertLess(result[0]['netRate'],-.10)

    def test_unfilled_exit_is_not_treated_as_known(self):
        t=np.array([0,1000,1400,1500,1600]);b=np.full(len(t),100.)
        trades, opened, _=execute_long_day(t,b,b+.01,[1000],9000,TimedExit(.05,.02,40000,.0005))
        self.assertEqual(trades,[]);self.assertEqual(opened['entryTime'],1400)

    def test_invalid_ema_pair(self):
        with self.assertRaises(ValueError):RunInput(rule='ema_cross',fast=32,slow=8)

    def test_accelerated_long_matches_existing_execution(self):
        rng=np.random.default_rng(17)
        for _ in range(24):
            t=np.arange(0,100_000,100)
            start=int(rng.integers(1000,88_000))
            t=t[(t<start)|(t>start+4200)]
            bid=100+np.cumsum(rng.normal(0,.08,len(t)))
            ask=bid+.03
            clock=np.arange(0,100_000,1000)
            sides=rng.integers(0,2,len(clock),dtype=np.int8)
            terms=TimedExit(.001,.0015,int(rng.integers(1500,7000)),.0005,
                            adverse=rng.choice([None,0.,.002]))
            old=execute_long_day(t,bid,ask,clock[sides==1],100_000,terms)
            new=execute_directional_day(t,bid,ask,clock,sides,100_000,terms,
                                        prepare_entries(t,clock,100_000,terms.delay_ms))
            for row in new[0]+([new[1]] if new[1] else []):self.assertEqual(row.pop('side'),'long')
            self.assertEqual(new,old)

    def test_short_target_and_shared_position(self):
        t=np.arange(0,7000,100)
        bid=np.full(len(t),100.)
        bid[t>=2600]=98
        ask=bid+.02
        clock=np.array([1000,2000,4000])
        sides=np.array([-1,1,1],dtype=np.int8)
        terms=TimedExit(.01,.03,4000,.0005)
        closed,_,_=execute_directional_day(t,bid,ask,clock,sides,7000,terms,
                                          prepare_entries(t,clock,7000,terms.delay_ms))
        short=closed[0]
        self.assertEqual((short['side'],short['decisionTime'],short['entryTime'],short['exitTime']),
                         ('short',1000,1300,2900))
        self.assertAlmostEqual(short['netRate'],(100*.9995-98.02*1.0005)/(100*1.0005))
        self.assertTrue(all(trade['decisionTime']!=2000 for trade in closed))


if __name__=='__main__':
    unittest.main()
