import unittest
from datetime import datetime, timedelta, timezone
from blackhorse_eval import (aware, integer, seed, closest, collect_ccu,
                             collect_reviews, score_one)

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

    def test_review_delta_uses_same_language_basis(self):
        basis="filter=updated;purchase_type=all;review_type=all;offtopic=0"
        samples=collect_reviews([
            {"AppID":"1478500","状态":"OK","语言口径":"all",
             "评论过滤口径":basis,"采样时间":LOCK.isoformat(),"累计评论":42139},
            {"AppID":"1478500","状态":"OK","语言口径":"schinese",
             "评论过滤口径":basis,"采样时间":(LOCK+timedelta(days=7)).isoformat(),"累计评论":4000},
            {"AppID":"1478500","状态":"OK","语言口径":"all",
             "评论过滤口径":basis,"采样时间":(LOCK+timedelta(days=7)).isoformat(),"累计评论":43000}
        ])
        result=score_one(forecast("1478500","成熟参照",baseline_reviews=42139),
                         {},samples,LOCK+timedelta(days=7,minutes=10))
        self.assertEqual(result[12],42139)
        self.assertEqual(result[13],861)
        self.assertIn("成熟对照",result[15])

    def test_mismatched_times_do_not_fabricate_7d(self):
        p=forecast("4847040",baseline_reviews=11)
        samples={"4847040":[(LOCK+timedelta(days=6),99)]}
        result=score_one(p,{},samples,LOCK+timedelta(days=8))
        self.assertEqual(result[13],"")
        self.assertNotIn("D7可复核",result[14])


if __name__=="__main__":
    unittest.main()
