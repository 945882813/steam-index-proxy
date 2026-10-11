# Steam Index Proxy

Render deployment proxy for Steam Index API.

Secrets are configured only in Render:
- STEAM_INDEX_API_KEY
- PROXY_TOKEN

Endpoints:
- GET /health
- GET /v1/apps/<appid>/players?range=7d&token=<PROXY_TOKEN>

Features:
- API key stays server-side
- AppID and range validation
- 10 minute cache
- basic rate limiting
