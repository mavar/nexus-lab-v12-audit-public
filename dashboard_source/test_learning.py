import unittest
import numpy as np

from lab_api import LearnInput
from math import prod
from learn_jobs import FIT,SELECT,entry_sides,grid
from learn_labels import features,labeled_returns,prepare
from learn_volume import rolling_volume


class LearningTests(unittest.TestCase):
    def test_volume_uses_only_received_trades(self):
        t=np.arange(1000,16001,1000)
        price=np.where(t<=10000,100.,101.)
        qty=np.where(t==9000,5.,1.)
        clock=np.array([8000,10000,12000])
        full=rolling_volume(t,price,qty,clock,np.full(3,100.),np.zeros(3),6000)
        prefix=rolling_volume(t[:10],price[:10],qty[:10],clock[:2],np.full(2,100.),np.zeros(2),6000)
        np.testing.assert_allclose(prefix,full[:2],atol=1e-12)
        self.assertAlmostEqual(full[1,0],np.log1p(6))
        self.assertAlmostEqual(full[1,1],np.log1p(10))
        self.assertAlmostEqual(full[1,3],1)

    def test_short_labels_and_competing_signals(self):
        t=np.arange(0,6000,100)
        bid=np.full(len(t),100.)
        bid[t>=2600]=98
        ask=bid+.02
        clock=np.array([1000])
        short=labeled_returns(t,bid,ask,clock,6000,3000,.01,.0005,prepare(t,-ask),-1)
        self.assertAlmostEqual(short[0],(100*.9995-98.02*1.0005)/(100*1.0005))
        ask[20]=102
        stopped=labeled_returns(t,bid,ask,clock,6000,3000,.01,.0005,prepare(t,-ask),-1)
        self.assertLess(stopped[0],0)
        np.testing.assert_array_equal(entry_sides({1:np.array([.4,.6,.2,.5]),-1:np.array([.6,.4,.1,.5])},.3),
                                      [-1,1,0,1])

    def test_features_do_not_change_when_future_is_removed(self):
        t=np.arange(0,250000,100,dtype=np.int64);b=100+np.sin(t/5000)/10;a=b+.01
        c,x=features(t,b,a)
        for cut in (710,1000,1800):
            ct,xt=features(t[:cut],b[:cut],a[:cut]);take=c<=t[cut-1]
            np.testing.assert_array_equal(c[take],ct);np.testing.assert_allclose(x[take],xt,rtol=0,atol=1e-13)

    def test_target_cost_delay_gap_and_adverse(self):
        t=np.arange(0,60000,100,dtype=np.int64); b=np.full(len(t),100.);a=b+.01
        b[(t>=7000)&(t<7500)]=100.5;a=b+.01
        clock=np.array([1000],dtype=np.int64)
        def target(q,bb,aa,h,d):return labeled_returns(q,bb,aa,clock,60000,h,d,.0005,prepare(q,bb))[0]
        self.assertLess(target(t,b,a,5000,.01),0)
        self.assertAlmostEqual(target(t,b,a,8000,.01),100.5*.9995/(100.01*1.0005)-1)
        bb=b.copy();bb[(t>=5000)&(t<6000)]=99.;aa=bb+.01
        self.assertLess(target(t,bb,aa,8000,.001),0)
        keep=(t<4000)|(t>=8000);self.assertTrue(np.isnan(target(t[keep],b[keep],a[keep],8000,.01)))

    def test_split_and_search_grid(self):
        self.assertLess(max(FIT),min(SELECT));self.assertEqual(len(FIT),4);self.assertEqual(len(SELECT),3)
        self.assertEqual(prod(map(len,grid(LearnInput()).values())),1)
        bounds=dict(holdSeconds=(120,240,2),targetPct=(.1,.15,2),dipPct=(.05,.08,2),
                    complexity=(2,4,6),confidencePct=(10,30,3),stopPct=(.15,.25,2))
        search={key:dict(lower=lo,upper=hi,points=n) for key,(lo,hi,n) in bounds.items()}
        def all_axes():return grid(LearnInput(model='tree',complexity=3,optimize=True,search=search))
        axes=all_axes()
        self.assertEqual(axes['complexity'],[2,3,4])
        self.assertEqual(axes['stopPct'],[.15,.25])
        self.assertEqual(prod(map(len,axes.values())),144)
        search['stopPct']=dict(lower=.2,upper=.2,points=1)
        self.assertEqual(all_axes()['stopPct'],[.2])
        search['holdSeconds']=dict(lower=15.2,upper=120,points=2)
        with self.assertRaises(ValueError):all_axes()


if __name__=='__main__':unittest.main()
