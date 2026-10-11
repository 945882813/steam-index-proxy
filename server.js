const http = require("http");

const PORT = process.env.PORT || 10000;
const API_KEY = process.env.STEAM_INDEX_API_KEY;
const PROXY_TOKEN = process.env.PROXY_TOKEN;
const BASE = "https://public-api.steamidx.com";

const cache = new Map();
const CACHE_MS = 10 * 60 * 1000;
const WINDOW_MS = 60 * 1000;
const MAX_REQ_PER_WINDOW = 30;
let requestTimes = [];

function json(res, status, body) {
  const data = JSON.stringify(body);
  res.writeHead(status, {"content-type":"application/json; charset=utf-8","cache-control":"no-store"});
  res.end(data);
}

function rateLimited() {
  const now = Date.now();
  requestTimes = requestTimes.filter(t => now - t < WINDOW_MS);
  if (requestTimes.length >= MAX_REQ_PER_WINDOW) return true;
  requestTimes.push(now);
  return false;
}

http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, `http://${req.headers.host}`);
    if (url.pathname === "/health") return json(res, 200, {ok:true, steamIndexKeyConfigured:Boolean(API_KEY), proxyTokenConfigured:Boolean(PROXY_TOKEN)});
    const m = url.pathname.match(/^\/v1\/apps\/(\d+)\/players$/);
    if (!m) return json(res,404,{error:"not_found"});
    if (!API_KEY || !PROXY_TOKEN) return json(res,503,{error:"service_not_configured"});
    if (url.searchParams.get("token") !== PROXY_TOKEN) return json(res,401,{error:"unauthorized"});
    if (rateLimited()) return json(res,429,{error:"proxy_rate_limited"});
    const appid=m[1];
    const range=url.searchParams.get("range")||"7d";
    if (!new Set(["24h","7d","30d","1y","all"]).has(range)) return json(res,400,{error:"invalid_range"});
    const key=`${appid}:${range}`;
    const cached=cache.get(key);
    if(cached && Date.now()-cached.ts<CACHE_MS){res.writeHead(200,{"content-type":"application/json","x-cache":"HIT"});return res.end(cached.body);}
    const r=await fetch(`${BASE}/v1/apps/${appid}/players?range=${encodeURIComponent(range)}`,{headers:{Authorization:`Bearer ${API_KEY}`,Accept:"application/json","User-Agent":"Steam-Indie-Radar/1.0"}});
    const body=await r.text();
    if(!r.ok)return json(res,r.status,{error:"steam_index_upstream_error",upstreamStatus:r.status});
    cache.set(key,{ts:Date.now(),body});
    res.writeHead(200,{"content-type":"application/json","x-cache":"MISS","x-data-source":"Steam Index"});
    res.end(body);
  } catch(e){json(res,500,{error:"internal_error"});}
}).listen(PORT,"0.0.0.0",()=>console.log(`steam-index-proxy listening on ${PORT}`));