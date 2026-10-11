import os
import json
import datetime
import requests
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')
STEAM_INDEX_KEY = os.environ.get('STEAM_INDEX_API_KEY')


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def open_sheet():
    info = json.loads(os.environ['GOOGLE_SERVICE_ACCOUNT_JSON'])
    creds = Credentials.from_service_account_info(
        info,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    return gspread.authorize(creds).open_by_key(SHEET_ID)


def steam_index(appid):
    if not STEAM_INDEX_KEY:
        return None, 'Missing API key'
    try:
        r = requests.get(
            f'https://public-api.steamidx.com/v1/apps/{appid}/players?range=7d',
            headers={'Authorization': f'Bearer {STEAM_INDEX_KEY}'},
            timeout=20,
        )
        if r.ok:
            return r.json(), 'OK'
        return None, f'HTTP {r.status_code}'
    except Exception as e:
        return None, str(e)[:200]


def extract_players(data):
    if not isinstance(data, dict):
        return None
    for key in ['current_players', 'players', 'ccu']:
        if key in data:
            return data[key]
    return None


def main():
    book = open_sheet()
    watch = book.worksheet('Watchlist').get_all_records()

    sample_rows = []
    errors = []
    now = utc_now()

    for item in watch:
        appid = str(item.get('AppID', '')).strip()
        if not appid:
            continue

        data, status = steam_index(appid)
        players = extract_players(data)

        sample_rows.append([
            now,
            appid,
            item.get('Game_Name', ''),
            players if players is not None else '',
            'Steam Index',
            '7d',
            status,
            json.dumps(data, ensure_ascii=False)[:500] if data else ''
        ])

        if status != 'OK':
            errors.append(f'{appid}: {status}')

    if sample_rows:
        book.worksheet('CCU_Samples').append_rows(sample_rows)

    run_status = 'OK' if not errors else 'PARTIAL'
    book.worksheet('Run_Log').append_row([
        now,
        'CCU Sampler',
        run_status,
        len(sample_rows),
        'Steam Index',
        'Steam fallback pending',
        'Completed',
        '; '.join(errors),
        now[:10],
        'CCU_Samples'
    ])


if __name__ == '__main__':
    main()
