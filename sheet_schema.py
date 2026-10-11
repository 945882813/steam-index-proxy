"""Steam 独立游戏雷达：中英双语兼容工作表结构。

列顺序和字段语义不变；中文用于展示，英文仅供代码向后兼容。
AppID / CCU / D1 等专有技术标识保持英文。
"""

SHEET_TITLES = {
    "README": "使用说明",
    "Games": "游戏库",
    "Daily_Snapshot": "每日快照",
    "CCU_Legacy": "CCU历史存档",
    "Review_Velocity": "评论增速",
    "Upcoming": "即将发行",
    "Design_Atoms": "玩法原子",
    "Trend_Atoms": "趋势原子",
    "Watchlist": "重点观察",
    "Daily_Report": "雷达日报",
    "Daily_Ranking": "每日排名",
    "Run_Log": "运行日志",
    "Settings": "系统设置",
    "CCU_Validated": "CCU可信样本",
    "CCU_Trend": "CCU增长趋势",
    "CCU_Samples": "CCU原始采样",
}

HEADERS_EN = {
    "Games": ["AppID", "Game_Name", "Release_State", "Release_Date", "Developer", "Publisher", "Broad_Indie_Confidence", "Global_Steam_URL", "China_Relevance", "First_Seen", "Last_Seen", "Primary_Source", "Notes", "CCU_Target_AppID", "CCU_Target_Type"],
    "Daily_Snapshot": ["Snapshot_Date", "AppID", "Game_Name", "Total_Reviews", "Positive_Reviews", "Negative_Reviews", "Positive_Rate", "Global_TopSeller_Rank", "China_TopSeller_Rank", "Price", "Discount_Pct", "Current_CCU", "Daily_Peak_CCU", "Update_or_Event", "Source_URL", "Confidence"],
    "CCU_Legacy": ["Sample_Time", "AppID", "Game_Name", "CCU", "Source", "Source_URL", "Status", "Error_or_Note"],
    "Review_Velocity": ["Calc_Time", "AppID", "Game_Name", "Positive_24h", "Negative_24h", "Reviews_24h", "Positive_7d_Avg", "Positive_30d_Avg", "Accel_vs_7d", "Accel_vs_30d", "Recent_Positive_Rate", "Simplified_CN_Positive_Rate", "Global_CN_Delta", "Source_URL"],
    "Upcoming": ["Snapshot_Date", "AppID", "Game_Name", "Release_Date", "Top_Wishlist_Rank", "Popular_Upcoming_Rank", "Rank_Change_1d", "Rank_Change_7d", "Demo_Available", "China_Signal", "Source_URL", "Notes"],
    "Design_Atoms": ["As_Of", "AppID", "Game_Name", "Atom_Category", "Atom", "Evidence_Type", "Evidence_Summary", "Evidence_URL", "AI_Confidence", "Player_Validated"],
    "Trend_Atoms": ["As_Of", "Trend_or_Atom", "Games_Count", "D1_Signal", "D7_Signal", "D30_Signal", "China_Delta", "Trend_Status", "Representative_AppIDs", "Evidence_Summary", "Confidence", "Next_Check"],
    "Watchlist": ["AppID", "Game_Name", "Priority", "Reason", "Start_Date", "Last_Review_Date", "Next_Action", "Status", "Owner_Note"],
    "Daily_Report": ["Report_Date", "Report_Type", "One_Line_Judgment", "Top10_AppIDs", "Emerging_Trends", "Breakout_Cases", "China_Delta_Summary", "Play_Next", "Source_Receipt", "Full_Report_Link_or_Text"],
    "Daily_Ranking": ["Report_Date", "Rank", "AppID", "Game_Name", "Innovation", "Underdog", "Player_Trend", "Commercial", "Radar_Score", "Confidence", "Why_Today", "China_Signal", "Action", "Primary_Source"],
    "Run_Log": ["Run_Time", "Task", "Status", "Rows_Written", "Primary_Source", "Fallback_Source", "Source_Status", "Error_or_Note", "Report_Date", "Sheet_Target"],
    "Settings": ["Key", "Value", "Status", "Notes"],
    "CCU_Validated": ["Sample_Time", "AppID", "Game_Name", "CCU", "Source", "Source_URL", "Data_Quality", "Sample_Key"],
    "CCU_Trend": ["As_Of", "AppID", "Game_Name", "CCU_Current", "CCU_24h_Ago", "Change_D1_Pct", "CCU_7d_Ago", "Change_D7_Pct", "CCU_30d_Ago", "Change_D30_Pct", "Data_Status", "Source"],
    "CCU_Samples": ["Sample_Time", "AppID", "Game_Name", "CCU", "Range", "Source", "Source_URL", "Data_Quality", "Status", "Error_or_Note", "Raw_Response"],
}

HEADERS_CN = {
    "Games": ["AppID", "游戏名称", "发行阶段", "发行日期", "开发商", "发行商", "独立游戏置信度", "Steam商店链接", "中国市场相关度", "首次发现", "最近观察", "主要来源", "备注", "采样目标AppID", "采样目标类型"],
    "Daily_Snapshot": ["快照日期", "AppID", "游戏名称", "评论总数", "好评数", "差评数", "好评率", "全球畅销榜排名", "中国畅销榜排名", "价格", "折扣比例", "当前CCU", "24小时峰值CCU", "更新或活动", "来源链接", "置信度"],
    "CCU_Legacy": ["采样时间", "AppID", "游戏名称", "CCU", "来源", "来源链接", "状态", "错误或备注"],
    "Review_Velocity": ["计算时间", "AppID", "游戏名称", "24小时好评", "24小时差评", "24小时评论数", "7日平均好评", "30日平均好评", "相对7日加速度", "相对30日加速度", "近期好评率", "简中好评率", "中外好评率差", "来源链接"],
    "Upcoming": ["快照日期", "AppID", "游戏名称", "发行日期", "愿望单榜排名", "热门即将推出排名", "榜单日变化", "榜单7日变化", "Demo是否可玩", "中国市场信号", "来源链接", "备注"],
    "Design_Atoms": ["截至日期", "AppID", "游戏名称", "原子类别", "玩法原子", "证据类型", "证据摘要", "证据链接", "AI置信度", "玩家验证"],
    "Trend_Atoms": ["截至日期", "趋势或原子", "涉及游戏数", "当日信号", "7日信号", "30日信号", "中国市场差异", "趋势状态", "代表AppID", "证据摘要", "置信度", "下次核验"],
    "Watchlist": ["AppID", "游戏名称", "优先级", "关注理由", "开始关注日期", "最近复核日期", "下一步动作", "状态", "负责人备注"],
    "Daily_Report": ["报告日期", "报告类型", "一句话判断", "Top10 AppID", "正在形成的趋势", "代表性案例", "中国市场差异摘要", "优先试玩", "来源清单", "完整报告"],
    "Daily_Ranking": ["报告日期", "排名", "AppID", "游戏名称", "创新分", "黑马潜力分", "玩家趋势分", "商业热度分", "雷达总分", "置信度", "今日上榜原因", "中国市场信号", "建议行动", "主要来源"],
    "Run_Log": ["运行时间", "任务", "状态", "写入行数", "首选数据源", "备用数据源", "数据源状态", "错误或备注", "报告日期", "目标工作表"],
    "Settings": ["配置项", "配置值", "状态", "备注"],
    "CCU_Validated": ["采样时间", "AppID", "游戏名称", "CCU", "来源", "来源链接", "数据质量", "样本唯一键"],
    "CCU_Trend": ["统计时间", "AppID", "游戏名称", "当前CCU", "24小时前CCU", "D1变化率", "7日前CCU", "D7变化率", "30日前CCU", "D30变化率", "数据状态", "来源"],
    "CCU_Samples": ["采样时间", "AppID", "游戏名称", "CCU", "采样范围", "来源", "来源链接", "数据质量", "状态", "错误或备注", "原始响应摘要"],
}

def worksheet(book, canonical_name):
    """Chinese first, with old English titles accepted during migration."""
    try:
        return book.worksheet(SHEET_TITLES[canonical_name])
    except Exception as error:
        try:
            return book.worksheet(canonical_name)
        except Exception:
            raise error


def header_language(canonical_name, actual):
    english, chinese = HEADERS_EN[canonical_name], HEADERS_CN[canonical_name]
    if actual[:len(english)] == english:
        return "en"
    if actual[:len(chinese)] == chinese:
        return "cn"
    raise ValueError(f"{canonical_name} header mismatch: refusing to write shifted columns")


def records(book, canonical_name):
    """Expose stable English field names regardless of user-facing display language."""
    ws = worksheet(book, canonical_name)
    head = ws.row_values(1)
    header_language(canonical_name, head)
    english = HEADERS_EN[canonical_name]
    out = []
    for record in ws.get_all_records():
        out.append({eng: record.get(actual, "") for eng, actual in zip(english, head)})
    return out


def output_headers(canonical_name, ws):
    """Use Chinese headers on Chinese tabs; keep English tabs backwards compatible."""
    return HEADERS_CN[canonical_name] if ws.title == SHEET_TITLES[canonical_name] else HEADERS_EN[canonical_name]
