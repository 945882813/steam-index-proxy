# CCU 数据字段规范｜中文展示版

长期工作表使用中文名称与表头；实际字段定义和中英映射维护在 `sheet_schema.py`。列顺序保持不变，避免旧数据漂移。所有 Github 脚本须经该映射读取数据；历史数据不更改数值。

- **CCU原始采样**：采样时间、AppID、游戏名称、CCU、采样范围、来源、来源链接、数据质量、状态、错误或备注、原始响应摘要。
- **CCU可信样本**：采样时间、AppID、游戏名称、CCU、来源、来源链接、数据质量、样本唯一键。
- **CCU增长趋势**：统计时间、AppID、游戏名称、当前CCU、24小时前CCU、D1变化率、7日前CCU、D7变化率、30日前CCU、D30变化率、数据状态、来源。
- **运行日志**：运行时间、任务、状态、写入行数、首选数据源、备用数据源、数据源状态、错误或备注、报告日期、目标工作表。

数值缺测不填0，单次CCU不代表增长。只从验证后的实际跨日样本计算D1/D7/D30，完整保留原始时间戳与数据来源。

---

# Steam Indie Radar CCU Schema - v2

## CCU_Legacy

Read-only old-format audit records, including cached pages and a set of truncated Steam Index API JSON responses. Never use this tab for trend calculations.

## CCU_Samples: raw observations

Column order (fixed):
1. Sample_Time - ISO-8601 timestamp with timezone
2. AppID - Steam app identifier
3. Game_Name
4. CCU - nonnegative integer or blank
5. Range - 7d for Steam Index request; current for official request
6. Source - Steam Index or Steam Official
7. Source_URL
8. Data_Quality - VERIFIED, INVALID, RECONSTRUCTED etc.
9. Status - OK, MISSING, SKIPPED_UNRELEASED, HISTORICAL_ONLY etc.
10. Error_or_Note - no credentials
11. Raw_Response - short sanitized summary, not the full time series

The previously misaligned 19 Steam Index API responses were standardized into CCU_Samples; 14 had parsable current CCU, five did not. All are RECONSTRUCTED / HISTORICAL_ONLY and excluded from verified trends because their observation freshness was not reestablished.

## CCU_Validated: derived and idempotent

Sample_Time | AppID | Game_Name | CCU | Source | Source_URL | Data_Quality | Sample_Key

Only accepts Status=OK, Data_Quality=VERIFIED or FRESH_FALLBACK, authenticated Steam Index or Steam Official source, numeric nonnegative CCU, timestamp with timezone and attributable URL. Sample_Key combines AppID, UTC instant and Source. Each run rebuilds the view rather than appending duplicate rows.

## CCU_Trend: derived and idempotent

As_Of | AppID | Game_Name | CCU_Current | CCU_24h_Ago | Change_D1_Pct | CCU_7d_Ago | Change_D7_Pct | CCU_30d_Ago | Change_D30_Pct | Data_Status | Source

Find an older verified point near 24 hours, 7 days or 30 days before the latest, with a tolerance of 3.25 hours for six-hour collection. Missing reference point or zero denominator means blank growth. CURRENT_ONLY is expected until enough historical samples accumulate. Percentage changes are decimals, e.g. 0.25 means +25%.

## Run_Log

Run_Time | Task | Status | Rows_Written | Primary_Source | Fallback_Source | Source_Status | Error_or_Note | Report_Date | Sheet_Target

Job success is not proof of valid CCU: always inspect numeric CCU, verified count and computed trend state. Legacy snapshots are for audit only.
