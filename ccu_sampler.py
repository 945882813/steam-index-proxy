import os
import json
import datetime
import requests
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')
STEAM_INDEX_KEY = os.environ.get('STEAM_INDEX_API_KEY')


def now_cn():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds')


def open_sheet():
    info = json.loads(os.environ['GOOGLE_SERVICE_ACCOUNT_JSON'])
    creds = Credentials.from_service_account_info(info, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return gspread.authorize(creds).open_by_key(SHEET_ID)


def steam_index(appid):
    if not STEAM_INDEX_KEY:
        return None, 'Steam Index API', '', 'BLOCKED_NO_KEY'
    try:
        r = requests.get(
            f'https://public-api.steamidx.com/v1/apps/{appid}/players?range=7d',
            headers={'Authorization': f'Bearer {STEAM_INDEX_KEY}'},
            timeout=20,
        )
        if r.ok:
            return r.json(), 'Steam Index', f'https://public-api.steamidx.com/v1/apps/{appid}/players?range=7d', 'VERIFIED'
        return None, 'Steam Index', '', f'HTTP_{r.status_code}'
    except Exception as e:
        return None, 'Steam Index', '', str(e)[:120]


def steam_official(appid):
    try:
        r = requests.get(
            f'https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={appid}',
            timeout=15,
        )
        if r.ok:
            return r.json(), 'Steam Official', f'https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={appid}', 'VERIFIED'
        return None, 'Steam Official', '', f'HTTP_{r.status_code}'
    except Exception as e:
        return None, 'Steam Official', '', str(e)[:120]


def extract_players(data):
    if not isinstance(data, dict):
        return None
    if isinstance(data.get('response'), dict):
        return data['response'].get('player_count')
    for key in ['current_players', 'players', 'ccu']:
        if key in data:
            return data[key]
    return None


def main():
    book = open_sheet()
    watch = book.worksheet('Watchlist').get_all_records()
    rows = []
    errors = []
    now = now_cn()

    for item in watch:
        appid = str(item.get('AppID', '')).strip()
        if not appid:
            continue

        data, source, url, quality = steam_index(appid)
        if data is None:
            data, source, url, quality = steam_official(appid)

        players = extract_players(data)
        status = 'OK' if players is not None else 'FAILED'

        rows.append([
            now,
            appid,
            item.get('Game_Name', ''),
            players if players is not None else '',
            'current' if source == 'Steam Official' else '7d',
            source,
            url,
            quality,
            status,
            quality if status != 'OK' else '',
            json.dumps(data, ensure_ascii=False)[:500] if data else ''
        ])

        if status != 'OK':
            errors.append(f'{appid}:{quality}')

    if rows:
        book.worksheet('CCU_Samples').append_rows(rows)

    book.worksheet('Run_Log').append_row([
        now,
        'CCU Sampler',
        'OK' if not errors else 'PARTIAL',
        len(rows),
        'Steam Index',
        'Steam Official',
        'Completed',
        '; '.join(errors),
        now[:10],
        'CCU_Samples'
    ])


if __name__ == '__main__':
    main()
