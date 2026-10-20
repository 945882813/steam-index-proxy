import unittest
from datetime import datetime, timedelta, timezone
from blackhorse_eval import (aware, integer, seed, closest, collect_ccu,
                             collect_reviews, locked_review_anchor, score_one)

UTC=timezone.utc
LOCK=datetime(2026,10,11,14,39,3,tzinfo=UTC)

def forecast(appid="3084460", stage="待发售", baseline_ccu="", baseline_reviews=""):
    return {
        "预测ID": "BH-TEST-"+appid,
        "基线锁定时间": LOCK.isoformat(),
        "AppID": appid,
        "游戏名称": "Fixture",
        "观察阶段": stage,
        "初始CCU": baseline_ccu,
        "初始评论总数": baseline_reviews,
    }

class BlackhorseEvaluationTest(unittest.TestCase):
    def test_int_numeric_and_aware(self):
        for value in ("",None,True,-1,"1.4","nan","inf"):
            self.assertIsNone(integer(value))
        self.assertEqual(integer("0"),0)
        self.assertEqual(integer(12),12)
        self.assertIsNone(aware("2026-10-11 22:39:03"))
        self.assertIsNotNone(aware("2026-10-11T22:39:03+08:00"))

    def test_d1_requires_actual_post_lock_baseline_and_a_second_day(self):
        app="3084460"
        samples={app:[(LOCK-timedelta(hours=2),999),(LOCK+timedelta(minutes=4),100),
                      (LOCK+timedelta(hours=23,minutes=59),150)]}
        first=score_one(forecast(),samples,{},LOCK+timedelta(hours=3))
        self.assertEqual(first[5],100)
        self.assertEqual(first[6],"")
        second=score_one(forecast(),samples,{},LOCK+timedelta(days=1,minutes=1))
        self.assertEqual(second[6],150)
        self.assertEqual(second[7],0.5)
        self.assertEqual(second[8],"")

    def test_no_zero_denominator_growth_or_invented_values(self):
        rows=score_one(forecast("4847040",baseline_ccu="0",baseline_reviews=11),
                       {"4847040":[(LOCK+timedelta(days=1),4)]},{},
                       LOCK+timedelta(days=1,minutes=1))
        self.assertEqual(rows[5],0)
        self.assertEqual(rows[6],4)
        self.assertEqual(rows[7],"")
        self.assertEqual(rows[12],11)
        self.assertEqual(rows[13],"")

    def test_only_same_app_validated_ccu(self):
        accepted=collect_ccu([
            {"AppID":"100","数据质量":"VERIFIED","来源":"Steam Official",
             "来源链接":"https://api.steampowered.com/players","采样时间":LOCK.isoformat(),"CCU":18},
            {"AppID":"101","数据质量":"RECONSTRUCTED","来源":"Steam Official",
             "来源链接":"https://api.steampowered.com/players","采样时间":LOCK.isoformat(),"CCU":45},
            {"AppID":"100","数据质量":"VERIFIED","来源":"Steam Index",
             "来源链接":"https://invalid.example/","采样时间":LOCK.isoformat(),"CCU":99}
        ])
        self.assertEqual(accepted,{"100":[(LOCK,18)]})

    def test_production_ccu_collector_preserves_source(self):
        accepted=collect_ccu([{
            "AppID":"123", "数据质量":"VERIFIED", "来源":"Steam Index",
            "来源链接":"https://public-api.steamidx.com/x",
            "采样时间":LOCK.isoformat(), "CCU":50
        }],with_source=True)
        self.assertEqual(accepted,{"123":[(LOCK,50,"Steam Index")]})

    def test_blackhorse_d7_refuses_cross_provider_ccu(self):
        app="4847040"
        t0=LOCK+timedelta(hours=7)
        data={app:[
            (t0,9,"Steam Index"),
            (t0+timedelta(days=1),2,"Steam Official"),
            (t0+timedelta(days=7),3,"Steam Official")
        ]}
        p=forecast(app, baseline_reviews=11)
        row=score_one(p,data,{},t0+timedelta(days=7,minutes=1))
        self.assertEqual(row[5],9)
        self.assertEqual(row[6],"")
        self.assertEqual(row[8],"")
        self.assertEqual(row[14],"跨日证据不足")
        self.assertIn("CCU同源匹配：Steam Index",row[15])

    def test_blackhorse_d7_preserves_real_same_source_and_evidence_time(self):
        app="4847040"
        t0=LOCK+timedelta(hours=7)
        d7=t0+timedelta(days=7,minutes=12)
        samples={app:[
            (t0,9,"Steam Index"),
            (t0+timedelta(days=1),2,"Steam Index"),
            (d7,3,"Steam Index"),
        ]}
        review={app:[(t0,11),(d7,11)]}
        row=score_one(forecast(app),samples,review,d7+timedelta(minutes=1))
        self.assertEqual(row[5],9)
        self.assertEqual(row[6],2)
        self.assertEqual(row[8],3)
        self.assertEqual(row[9],-0.666667)
        self.assertEqual(row[13],0)
        self.assertIn("D7可复核",row[14])
        self.assertIn("CCU_D7采样=",row[15])

    def test_locked_baseline_without_source_is_not_compared_to_real_source_samples(self):
        app="4847040"
        t0=LOCK+timedelta(days=1)
        data={app:[(t0,12,"Steam Official")]}
        row=score_one(forecast(app,baseline_ccu=9),data,{},t0+timedelta(minutes=1))
        self.assertEqual(row[5],9)
        self.assertEqual(row[6],"")
        self.assertIn("锁定CCU未附可核验来源",row[15])

    def test_review_delta_uses_same_language_basis(self):
        basis="filter=updated;purchase_type=all;review_type=all;offtopic=0"
        samples=collect_reviews([
            {"AppID":"1478500","状态":"OK","语言口径":"all",
             "评论过滤口径":basis,"采样时间":LOCK.isoformat(),"累计评论":42139},
            {"AppID":"1478500","状态":"OK","语言口径":"schinese",
             "评论过滤口径":basis,"采样时间":(LOCK+timedelta(days=7)).isoformat(),"累计评论":4000},
            {"AppID":"1478500","状态":"OK","语言口径":"all",
             "评论过滤口径":basis,"采样时间":(LOCK-timedelta(minutes=20)).isoformat(),"累计评论":42139},
            {"AppID":"1478500","状态":"OK","语言口径":"all",
             "评论过滤口径":basis,"采样时间":(LOCK+timedelta(days=7)).isoformat(),"累计评论":43000}
        ])
        result=score_one(forecast("1478500","成熟参照",baseline_reviews=42139),
                         {},samples,LOCK+timedelta(days=7,minutes=10))
        self.assertEqual(result[12],42139)
        self.assertEqual(result[13],861)
        self.assertIn("成熟对照",result[15])

    def test_seven_day_review_window_matches_real_daily_0820_sampling(self):
        basis="filter=updated;purchase_type=all;review_type=all;offtopic=0"
        next_sample=LOCK+timedelta(days=7,hours=9,minutes=40)
        samples=collect_reviews([{
            "AppID":"4847040","状态":"OK","语言口径":"all",
            "评论过滤口径":basis,"采样时间":(LOCK-timedelta(minutes=20)).isoformat(),
            "累计评论":11
        },{
            "AppID":"4847040","状态":"OK","语言口径":"all",
            "评论过滤口径":basis,"采样时间":next_sample.isoformat(),
            "累计评论":29
        }])
        row=score_one(forecast("4847040",baseline_reviews=11),{},samples,next_sample+timedelta(minutes=1))
        self.assertEqual(row[13],18)
        self.assertIn("近似",row[15])

    def test_locked_review_baseline_requires_prelock_matching_official_sample(self):
        app="4847040"
        p=forecast(app,baseline_reviews=11)
        bad={
            app:[(LOCK-timedelta(minutes=20),12),
                 (LOCK+timedelta(days=7),50)]
        }
        row=score_one(p,{},bad,LOCK+timedelta(days=8))
        self.assertEqual(row[12],11)  # Immutable locked prediction remains shown
        self.assertEqual(row[13],"")  # Unsupported D7 delta is NOT published
        self.assertIn("锁定评论累计数未找到",row[15])
        self.assertIn("E0_INSUFFICIENT_D7",row[15])
        self.assertIsNone(locked_review_anchor(bad[app],LOCK,11))
        # A future sample of the same number also cannot establish the lock.
        after={app:[(LOCK+timedelta(minutes=1),11),
                    (LOCK+timedelta(days=7),50)]}
        self.assertEqual(score_one(p,{},after,LOCK+timedelta(days=8))[13],"")

    def test_d7_evidence_tiers_do_not_mean_forecast_success(self):
        app="4847040"
        t0=LOCK+timedelta(hours=2)
        cs={app:[(t0,9,"Steam Index"),
                 (t0+timedelta(days=7),3,"Steam Index")]}
        rs={app:[(LOCK-timedelta(minutes=20),11),
                 (LOCK+timedelta(days=7),11)]}
        row=score_one(forecast(app,baseline_reviews=11),cs,rs,
                      LOCK+timedelta(days=8))
        self.assertEqual(row[13],0)
        self.assertIn("E1_LOW_BASE",row[15])
        self.assertIn("评论_D7采样=",row[15])
        self.assertIn("评论基线样本=",row[15])
        mature=forecast(app,stage="成熟参照",baseline_reviews=11)
        self.assertIn("E1_REFERENCE_ONLY",score_one(mature,cs,rs,LOCK+timedelta(days=8))[15])

    def test_mismatched_times_do_not_fabricate_7d(self):
        p=forecast("4847040",baseline_reviews=11)
        samples={"4847040":[(LOCK+timedelta(days=6),99)]}
        result=score_one(p,{},samples,LOCK+timedelta(days=8))
        self.assertEqual(result[13],"")
        self.assertNotIn("D7可复核",result[14])


if __name__=="__main__":
    unittest.main()
