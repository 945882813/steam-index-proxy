import os
import datetime
import requests
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')
STEAM_INDEX_KEY = os.environ.get('STEAM_INDEX_API_KEY')


def sheet():
    creds = Credentials.from_service_account_info(
        eval(os.environ['GOOGLE_SERVICE_ACCOUNT_JSON']),
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    return gspread.authorize(creds).open_by_key(SHEET_ID)


def steam_index(appid):
    if not STEAM_INDEX_KEY:
        return None
    r = requests.get(
        f'https://public-api.steamidx.com/v1/apps/{appid}/players?range=7d',
        headers={'Authorization': f'Bearer {STEAM_INDEX_KEY}'},
        timeout=20,
    )
    if r.ok:
        return r.json()
    return None


def main():
    book = sheet()
    watch = book.worksheet('Watchlist').get_all_records()
    rows = []
    now = datetime.datetime.utcnow().isoformat()
    for item in watch:
        appid = str(item.get('AppID', '')).strip()
        if not appid:
            continue
        data = steam_index(appid)
        rows.append([now, appid, item.get('Game_Name',''), str(data), 'Steam Index', '', 'OK' if data else 'Missing', ''])
    if rows:
        book.worksheet('CCU_Samples').append_rows(rows)
    book.worksheet('Run_Log').append_row([now, 'CCU Sampler', 'OK', len(rows), 'Steam Index', 'Steam', 'Completed', '', now[:10], 'CCU_Samples'])


if __name__ == '__main__':
    main()
