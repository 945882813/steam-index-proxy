"""AI剧热度雷达：Google Sheet 中英字段映射。"""

SHEET_TITLES = {
    "Works": "作品库",
    "Episodes": "剧集目录",
    "Raw_Samples": "原始采样",
    "Validated_Samples": "可信样本",
    "Hongguo_Raw": "红果日榜原始",
    "Daily_Snapshot": "每日快照",
    "Trend": "增长趋势",
    "Daily_Ranking": "每日排名",
    "History": "历史热度",
    "Watchlist": "重点观察",
    "Daily_Report": "雷达日报",
    "Run_Log": "运行日志",
    "Settings": "系统设置",
}

HEADERS_EN = {
    "Works": ["Work_Key","Platform","IP_Name","Display_Name","Creator","Creator_ID","Identity_Grade","AI_Evidence","Serial_Status","First_Seen","Last_Seen","Canonical_Work_URL","Status","Notes"],
    "Episodes": ["Episode_Key","Work_Key","Platform","Season","Episode_No","Episode_Title","Canonical_ID","Canonical_URL","Published_At","Formal","Excluded_Reason","Last_Verified"],
    "Raw_Samples": ["Sample_Time","Platform","Work_Key","Episode_Key","Object_Type","V","C","F","T","L","D","Raw_V","Raw_C","Raw_F","Raw_T","Raw_L","Raw_D","Source_Tier","Source_URL","Snapshot_Observed_At","Published_At","Data_Quality","Status","Lower_Bound_Fields","Error_or_Note","Raw_Response_Summary"],
    "Validated_Samples": ["Sample_Time","Platform","Work_Key","Episode_Key","V","C","F","T","L","D","Source_Tier","Source_URL","Snapshot_Observed_At","Data_Quality","Sample_Key","Lower_Bound_Fields"],
    "Hongguo_Raw": ["Sample_Time","Update_Date","Raw_Rank","Title","Season_Hint","F","L","Page","Source_URL","Status","Row_Key"],
    "Daily_Snapshot": ["Snapshot_Date","Platform","Work_Key","IP_Name","V_Total","C_Total","F_Total","T_Total","L_Total","D_Total","Total_Score","Typical_Score","Recent_Score","Radar_Score","Score_Low","Score_High","Model_Mode","Freshness_Status","Confidence","Primary_Source"],
    "Trend": ["As_Of","Platform","Work_Key","IP_Name","Current_Score","D1_Score_Change","D7_Score_Change","D30_Score_Change","Rank_Current","Rank_D1","Rank_D7","Rank_D30","Days_TopN_30d","Peak_Rank_All_Time","Peak_Score_All_Time","Hot_Status","Data_Status"],
    "Daily_Ranking": ["Report_Date","Platform","Rank","Work_Key","IP_Name","Radar_Score","Score_Low","Score_High","Model_Mode","Confidence","Freshness_Status","Why_Today","Primary_Source"],
    "History": ["Platform","Work_Key","IP_Name","Creator","First_Ranked_Date","Last_Ranked_Date","Best_Rank","Best_Rank_Date","Peak_Score","Peak_Score_Date","Days_Top20","Days_Top5","Current_Rank","Current_Score","Current_Status","Consecutive_Ranked_Days","Resurgence_Count","Last_Updated"],
    "Watchlist": ["Work_Key","Platform","IP_Name","Priority","Reason","Start_Date","Last_Review_Date","Next_Action","Status","Owner_Note"],
    "Daily_Report": ["Report_Date","Report_Type","One_Line_Judgment","Bili_Top20_Keys","Douyin_Top20_Keys","Hongguo_Top5_Keys","New_Breakouts","Resurgences","Long_Term_Hot","Data_Quality_Summary","Full_Report"],
    "Run_Log": ["Run_Time","Task","Status","Rows_Written","Primary_Source","Fallback_Source","Source_Status","Error_or_Note","Report_Date","Sheet_Target"],
    "Settings": ["Key","Value","Status","Notes"],
}

HEADERS_CN = {
    "Works": ["Work_Key","平台","IP名称","展示名称","创作者/制作方","Creator_ID","身份等级","AI证据","连续剧状态","首次发现","最近观察","第一方作品入口","状态","备注"],
    "Episodes": ["Episode_Key","Work_Key","平台","季","集号","正片标题","Canonical_ID","Canonical_URL","发布时间","是否正式正片","排除原因","最近核验"],
    "Raw_Samples": ["采样时间","平台","Work_Key","Episode_Key","对象类型","V播放","C投币","F收藏","T分享","L点赞","D弹幕","原始V","原始C","原始F","原始T","原始L","原始D","来源层级","来源URL","快照观察时间","发布时间","数据质量","状态","下界字段","错误或备注","原始响应摘要"],
    "Validated_Samples": ["采样时间","平台","Work_Key","Episode_Key","V播放","C投币","F收藏","T分享","L点赞","D弹幕","来源层级","来源URL","快照观察时间","数据质量","样本唯一键","下界字段"],
    "Hongguo_Raw": ["采样时间","榜单日期","原始名次","作品标题","季提示","F收藏","L点赞","页码","来源URL","状态","Row_Key"],
    "Daily_Snapshot": ["快照日期","平台","Work_Key","IP名称","V_Total","C_Total","F_Total","T_Total","L_Total","D_Total","Total分","Typical分","Recent分","Radar_Score","分数下界","分数上界","模型模式","新鲜度状态","置信度","主要来源"],
    "Trend": ["统计时间","平台","Work_Key","IP名称","当前分数","D1分数变化","D7分数变化","D30分数变化","当前名次","D1名次","D7名次","D30名次","近30日TopN天数","历史最佳名次","历史峰值分","热度状态","数据状态"],
    "Daily_Ranking": ["报告日期","平台","排名","Work_Key","IP名称","Radar_Score","分数下界","分数上界","模型模式","置信度","新鲜度状态","今日上榜原因","主要来源"],
    "History": ["平台","Work_Key","IP名称","创作者/制作方","首次上榜日期","最近上榜日期","历史最佳名次","最佳名次日期","历史峰值分","峰值日期","Top20累计天数","Top5累计天数","当前名次","当前分数","当前状态","连续上榜天数","回潮次数","最后更新"],
    "Watchlist": ["Work_Key","平台","IP名称","优先级","关注理由","开始关注日期","最近复核日期","下一步动作","状态","备注"],
    "Daily_Report": ["报告日期","报告类型","一句话判断","B站Top20 Work_Key","抖音Top20 Work_Key","红果Top5 Work_Key","新爆发","回潮作品","长期热门","数据质量摘要","完整报告"],
    "Run_Log": ["运行时间","任务","状态","写入行数","首选数据源","备用数据源","数据源状态","错误或备注","报告日期","目标工作表"],
    "Settings": ["配置项","配置值","状态","备注"],
}

def worksheet(book, canonical_name):
    return book.worksheet(SHEET_TITLES[canonical_name])

def header_language(canonical_name, actual):
    en, cn = HEADERS_EN[canonical_name], HEADERS_CN[canonical_name]
    if actual[:len(en)] == en:
        return "en"
    if actual[:len(cn)] == cn:
        return "cn"
    raise ValueError(f"{canonical_name} header mismatch: {actual[:5]}")

def records(book, canonical_name):
    ws = worksheet(book, canonical_name)
    head = ws.row_values(1)
    header_language(canonical_name, head)
    en = HEADERS_EN[canonical_name]
    rows = []
    for rec in ws.get_all_records():
        rows.append({e: rec.get(a, "") for e, a in zip(en, head)})
    return rows
