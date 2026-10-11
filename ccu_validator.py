import os
import datetime
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')


def open_sheet():
    import json
    info = json.loads(os.environ['GOOGLE_SERVICE_ACCOUNT_JSON'])
    creds = Credentials.from_service_account_info(
        info,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    return gspread.authorize(creds).open_by_key(SHEET_ID)


def main():
    book = open_sheet()
    source = book.worksheet('CCU_Samples')
    records = source.get_all_records()

    valid = []
    for row in records:
        quality = str(row.get('Data_Quality', '')).upper()
        status = str(row.get('Status', '')).upper()
        if quality in ['VERIFIED', 'FRESH_FALLBACK'] and status == 'OK':
            valid.append([
                row.get('Sample_Time', ''),
                row.get('AppID', ''),
                row.get('Game_Name', ''),
                row.get('CCU', ''),
                row.get('Source', ''),
                row.get('Data_Quality', '')
            ])

    try:
        target = book.worksheet('CCU_Validated')
    except Exception:
        target = book.add_worksheet(title='CCU_Validated', rows=1000, cols=6)
        target.append_row(['Sample_Time','AppID','Game_Name','CCU','Source','Data_Quality'])

    if valid:
        target.append_rows(valid)


if __name__ == '__main__':
    main()
