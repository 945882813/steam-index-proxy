# CCU Data Schema

## CCU_Samples

Raw collection table.

Columns:

1. Sample_Time
2. AppID
3. Game_Name
4. CCU
5. Range
6. Source
7. Source_URL
8. Data_Quality
9. Status
10. Error_or_Note
11. Raw_Response

## CCU_Validated

Analysis-ready table.

Only includes:

- Data_Quality = VERIFIED
- Data_Quality = FRESH_FALLBACK
- Status = OK

Used by:

- Daily ranking
- Trend detection
- Black horse discovery
