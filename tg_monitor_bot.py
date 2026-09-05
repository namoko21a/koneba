import asyncio
import json
import os
import time
import aiohttp
from aiohttp import web
from datetime import datetime, timezone, timedelta

PHT = timezone(timedelta(hours=8))  # Philippines Time / Manila (UTC+8)


def now_pht(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Return current time formatted in Philippines Time (UTC+8, Manila)."""
    return datetime.now(PHT).strftime(fmt)


# ─── Shared in-memory state — updated each cycle, served via /status ───────
LATEST_DATA: dict = {
    "cycle":         0,
    "timestamp":     None,
    "online":        False,
    "services":      {"saveOpt": False, "phoneAuth": False},
    "homepage":      {},
    "indexInfo":     {},
    "phoneAccounts": [],
}

INTERVAL   = 30
TG_TOKEN   = "8889006993:AAEmCC3idYlvUK1hMP-c2Qtp_U2fGKVKQQo"
TG_CHAT_ID = "5295241896"
TG_API     = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
TG_UPDATES = f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates"

# ─── Bot control state ───────────────────────────────────────────────────────
monitoring_active: bool = False   # True while the monitoring loop should run
_last_update_id:   int  = 0       # Tracks Telegram long-poll offset

LOGIN_URL  = "https://www.hexmos.cfd/app-server/app/v1/user/login"
SAVE_OPT   = "https://www.hexmos.cfd/app-server/app/v1/account/saveOpt"
PHONE_AUTH = "https://www.hexmos.cfd/app-server/app/v1/account/phoneAuth"
INDEX_INFO = "https://www.hexmos.cfd/app-server/app/v1/user/indexInfo"
HOMEPAGE   = "https://www.hexmos.cfd/app-server/app/v1/user/personalHomepage"
PHONE_PAGE = "https://www.hexmos.cfd/app-server/app/v1/user-phone/page"

LOGIN_PAYLOAD = {
    "password":    "3e6c93d0ce9f76c44b63e1690da75fbc",
    "phoneNumber": "+639945850063",
}

LOGIN_HEADERS = {
    "User-Agent":       "okhttp/3.12.13",
    "Accept":           "application/json",
    "Accept-Encoding":  "gzip",
    "Content-Type":     "application/json",
    "accept-language":  "en-US",
    "request-paycode":  "Gcash",
    "client-platform":  "Android",
    "skip-url-manager": "true",
}


def log(tag: str, msg: str):
    ts = now_pht("%H:%M:%S")
    print(f"  [{ts}] {tag:<14} {msg}")


def divider(title: str = ""):
    line = "─" * 60
    print(f"\n{'─'*60}")
    if title:
        print(f"  {title}")
        print(line)


async def tg_send(session: aiohttp.ClientSession, text: str):
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        async with session.post(TG_API, json=payload) as resp:
            if resp.status != 200:
                print(f"  [TG] Warning: {resp.status} → {await resp.text()}")
    except Exception as e:
        print(f"  [TG] Error: {e}")


def login():
    import requests
    divider("LOGIN")
    resp = requests.post(LOGIN_URL, data=json.dumps(LOGIN_PAYLOAD), headers=LOGIN_HEADERS)
    data = resp.json()
    if data.get("code") != "0":
        raise RuntimeError(f"Login failed → {resp.text}")
    auth_token = data["data"]["authToken"]
    device_id  = data["data"]["deviceId"]
    log("✓ LOGIN", f"deviceId: {device_id}")
    return auth_token, device_id


def re_login(auth_state: dict):
    """Re-authenticate and refresh auth_state in-place (called on 406)."""
    log("⚠ RE-LOGIN", "Got 406 — fetching new authorization token...")
    auth_token, device_id = login()
    auth_state["headers"]      = build_headers(auth_token, device_id)
    save_opt, phone_auth       = build_payloads(device_id)
    auth_state["save_opt"]     = save_opt
    auth_state["phone_auth"]   = phone_auth
    log("✓ RE-LOGIN", "New token acquired — resuming.")


def build_headers(auth_token: str, device_id: str) -> dict:
    return {
        "User-Agent":      "okhttp/3.12.13",
        "Accept-Encoding": "gzip",
        "authorization":   auth_token,
        "accept-language": "zh-TW",
        "deviceid":        device_id,
        "request-paycode": "Gcash",
        "client-platform": "Android",
        "content-type":    "application/json; charset=utf-8",
    }


def build_payloads(device_id: str) -> tuple:
    save_opt = {
        "deviceId": device_id,
        "phone":    "09245831982",
        "smsList":  [],
        "userNo":   "AUN000000000017549",
    }
    phone_auth = {
        "authMode":         "hide",
        "phone":            "09245831982",
        "deviceId":         device_id,
        "smsPhone":         "09245831982",
        "permissionResult": "True",
        "userNo":           "AUN000000000017549",
    }
    return save_opt, phone_auth


async def call_save_opt(
    session: aiohttp.ClientSession,
    auth_state: dict,
) -> tuple:
    headers = auth_state["headers"]
    payload = auth_state["save_opt"]
    async with session.post(SAVE_OPT, data=json.dumps(payload), headers=headers) as resp:
        status = resp.status
        if status == 406:
            log("saveOpt", "406 received — re-authenticating...")
            re_login(auth_state)
            # Retry once with fresh credentials
            async with session.post(
                SAVE_OPT,
                data=json.dumps(auth_state["save_opt"]),
                headers=auth_state["headers"],
            ) as retry:
                status = retry.status
        ok = status == 200
        tg = f"  saveOpt      :  <b>ONLINE</b>  [{status} OK]\n" if ok else f"  saveOpt      :  [{status}]\n"
        return tg, ok


async def call_phone_auth(
    session: aiohttp.ClientSession,
    auth_state: dict,
) -> tuple:
    headers = auth_state["headers"]
    payload = auth_state["phone_auth"]
    async with session.post(PHONE_AUTH, data=json.dumps(payload), headers=headers) as resp:
        status = resp.status
        if status == 406:
            log("phoneAuth", "406 received — re-authenticating...")
            re_login(auth_state)
            # Retry once with fresh credentials
            async with session.post(
                PHONE_AUTH,
                data=json.dumps(auth_state["phone_auth"]),
                headers=auth_state["headers"],
            ) as retry:
                status = retry.status
        ok = status == 200
        tg = f"  phoneAuth    :  <b>ONLINE</b>  [{status} OK]\n" if ok else f"  phoneAuth    :  [{status}]\n"
        return tg, ok


async def call_index_info(
    session: aiohttp.ClientSession,
    auth_state: dict,
) -> tuple:
    headers = auth_state["headers"]
    async with session.get(INDEX_INFO, headers=headers) as resp:
        status = resp.status
        if status == 406:
            log("indexInfo", "406 received — re-authenticating...")
            re_login(auth_state)
            async with session.get(INDEX_INFO, headers=auth_state["headers"]) as retry:
                status = retry.status
                text   = await retry.text()
        else:
            text = await resp.text()
        try:
            if status != 200:
                raise ValueError(f"status {status}")
            d           = json.loads(text).get("data", {})
            self_income = float(d.get("selfIncome", 0))
            team_income = float(d.get("teamIncome", 0))
            tg = (
                "<b>▌ INDEX INFO</b>\n"
                "<code>────────────────────────────────</code>\n"
                f"  Today's individual total earnings  :  <b>{self_income:,.2f}</b>\n"
                f"  Today's Team Earnings              :  <b>{team_income:,.2f}</b>\n"
                "<code>────────────────────────────────</code>\n"
                f"  Today's personal order count       :  <b>{d.get('selfOrderQty', 'N/A')}</b>\n"
                f"  Today's team order count           :  <b>{d.get('teamOrderQty', 'N/A')}</b>\n"
                "<code>────────────────────────────────</code>\n"
                f"  Number of personal accounts        :  <b>{d.get('selfAccountNum', 'N/A')}</b>\n"
                f"  Number of team accounts            :  <b>{d.get('teamAccountNum', 'N/A')}</b>\n"
            )
            data = {
                "selfIncome":    self_income,
                "teamIncome":    team_income,
                "selfOrderQty":  d.get("selfOrderQty", "N/A"),
                "teamOrderQty":  d.get("teamOrderQty", "N/A"),
                "selfAccountNum": d.get("selfAccountNum", "N/A"),
                "teamAccountNum": d.get("teamAccountNum", "N/A"),
            }
            return tg, True, data
        except Exception:
            return f"<b>INDEX INFO</b>  [{status}]\n", False, {}


async def call_homepage(
    session: aiohttp.ClientSession,
    auth_state: dict,
) -> tuple:
    headers = auth_state["headers"]
    async with session.post(HOMEPAGE, headers=headers) as resp:
        status = resp.status
        if status == 406:
            log("homepage", "406 received — re-authenticating...")
            re_login(auth_state)
            async with session.post(HOMEPAGE, headers=auth_state["headers"]) as retry:
                status = retry.status
                text   = await retry.text()
        else:
            text = await resp.text()
        try:
            if status != 200:
                raise ValueError(f"status {status}")
            d      = json.loads(text).get("data", {})
            avl    = float(d.get("avlBalance", 0))
            freeze = float(d.get("freezeBalance", 0))
            total  = avl + freeze
            income = float(d.get("income", 0))
            tg = (
                "<b>▌ HOMEPAGE</b>\n"
                "<code>────────────────────────────────</code>\n"
                f"  Deposit              :  <b>{avl:,.2f}</b>\n"
                f"  Wallet Total Balance :  <b>{freeze:,.2f}</b>\n"
                f"  Total Balance        :  <b>{total:,.2f}</b>\n"
                "<code>────────────────────────────────</code>\n"
                f"  Income               :  <b>{income:,.2f}</b>\n"
            )
            data = {
                "deposit":       avl,
                "walletBalance": freeze,
                "totalBalance":  total,
                "income":        income,
            }
            return tg, True, data
        except Exception:
            return f"<b>HOMEPAGE</b>  [{status}]\n", False, {}


PHONE_PAGE_PAYLOAD = {
    "orderByType": "",
    "pageSize":    10,
    "orderBy":     "",
    "groupBy":     "",
    "pageNum":     1,
}


async def call_phone_page(
    session: aiohttp.ClientSession,
    auth_state: dict,
) -> tuple:
    headers = auth_state["headers"]
    async with session.post(PHONE_PAGE, data=json.dumps(PHONE_PAGE_PAYLOAD), headers=headers) as resp:
        status = resp.status
        if status == 406:
            log("phonePage", "406 received — re-authenticating...")
            re_login(auth_state)
            async with session.post(
                PHONE_PAGE,
                data=json.dumps(PHONE_PAGE_PAYLOAD),
                headers=auth_state["headers"],
            ) as retry:
                status = retry.status
                text   = await retry.text()
        else:
            text = await resp.text()
        try:
            if status != 200:
                raise ValueError(f"status {status}")
            STATUS_MAP = {
                "啟用": "enabled",
                "停用": "disabled",
                "enabled": "enabled",
                "disabled": "disabled",
            }
            items = json.loads(text).get("data", {}).get("list", [])
            rows = ""
            for item in items:
                phone      = item.get("phone", "N/A")
                bank       = item.get("associatedBank", "N/A")
                raw_status = item.get("phoneStatusName", "N/A")
                ph_status  = STATUS_MAP.get(raw_status, raw_status)
                day_income = float(item.get("dayIncome", 0))
                balance    = float(item.get("actualBalance", 0))
                rows += (
                    f"  📱 <b>{phone}</b>  [{bank}]\n"
                    f"     Status      :  <b>{ph_status}</b>\n"
                    f"     Day Income  :  <b>{day_income:,.2f}</b>\n"
                    f"     Balance     :  <b>{balance:,.2f}</b>\n"
                    f"<code>────────────────────────────────</code>\n"
                )
            if not rows:
                rows = "  (no phone accounts found)\n"
            tg = (
                "<b>▌ PHONE ACCOUNTS</b>\n"
                "<code>────────────────────────────────</code>\n"
                + rows
            )
            phone_list = [
                {
                    "phone":     item.get("phone", "N/A"),
                    "bank":      item.get("associatedBank", "N/A"),
                    "status":    STATUS_MAP.get(item.get("phoneStatusName", ""), item.get("phoneStatusName", "N/A")),
                    "dayIncome": float(item.get("dayIncome", 0)),
                    "balance":   float(item.get("actualBalance", 0)),
                }
                for item in items
            ]
            return tg, True, phone_list
        except Exception:
            return f"<b>PHONE ACCOUNTS</b>  [{status}]\n", False, []


def print_status_dashboard(cycle: int, statuses: dict):
    """Print a colour-coded KMPay status dashboard to the console."""
    OK  = "\033[92m●  OK    \033[0m"
    ERR = "\033[91m●  ERROR \033[0m"
    overall = all(statuses.values())
    banner  = "\033[92m  ✔  KMPay is WORKING\033[0m" if overall else "\033[91m  ✘  KMPay has ERRORS\033[0m"
    line    = "─" * 44
    print(f"\n  {line}")
    print(f"  {'KMPAY STATUS DASHBOARD':^42}")
    print(f"  Cycle #{cycle}  ·  {now_pht()} PHT")
    print(f"  {line}")
    for name, ok in statuses.items():
        indicator = OK if ok else ERR
        print(f"  {indicator}  {name}")
    print(f"  {line}")
    print(f"{banner}")
    print(f"  {line}\n")


async def run_cycle(auth_state: dict, cycle: int):
    headers = auth_state["headers"]

    async with aiohttp.ClientSession() as session:
        ts = now_pht()

        # saveOpt & phoneAuth handle 406 internally and update auth_state
        (save_opt_sec, ok_save_opt)     = await call_save_opt(session, auth_state)
        (phone_auth_sec, ok_phone_auth) = await call_phone_auth(session, auth_state)

        # Refresh headers in case re-login happened
        headers = auth_state["headers"]

        (
            (index_sec, ok_index, index_data),
            (homepage_sec, ok_homepage, homepage_data),
            (phone_page_sec, ok_phone_page, phone_accounts),
        ) = await asyncio.gather(
            call_index_info(session, auth_state),
            call_homepage(session, auth_state),
            call_phone_page(session, auth_state),
        )

        # Update shared state for the web dashboard
        LATEST_DATA.update({
            "cycle":         cycle,
            "timestamp":     ts,
            "online":        ok_save_opt and ok_phone_auth,
            "services":      {"saveOpt": ok_save_opt, "phoneAuth": ok_phone_auth},
            "homepage":      homepage_data,
            "indexInfo":     index_data,
            "phoneAccounts": phone_accounts,
        })

        print_status_dashboard(cycle, {
            "saveOpt     ": ok_save_opt,
            "phoneAuth   ": ok_phone_auth,
            "indexInfo   ": ok_index,
            "homepage    ": ok_homepage,
            "phonePage   ": ok_phone_page,
        })

        msg = (
            f"<b>▌ KMPAY MONITOR  —  CYCLE #{cycle}</b>\n"
            f"<code>────────────────────────────────</code>\n"
            f"  Time         :  {ts}\n"
            f"<code>────────────────────────────────</code>\n"
            f"<b>▌ SERVICE STATUS</b>\n"
            f"<code>────────────────────────────────</code>\n"
            f"{save_opt_sec}"
            f"{phone_auth_sec}"
            f"<code>────────────────────────────────</code>\n"
            f"{homepage_sec}"
            f"<code>────────────────────────────────</code>\n"
            f"{index_sec}"
            f"<code>────────────────────────────────</code>\n"
            f"{phone_page_sec}"
            f"<code>────────────────────────────────</code>"
        )
        await tg_send(session, msg)

    print(f"  Next cycle in {INTERVAL}s...\n")


# ─── Web API ────────────────────────────────────────────────────────────────

async def status_handler(request: web.Request) -> web.Response:
    """GET /status — returns the latest cycle data as JSON."""
    headers = {
        "Access-Control-Allow-Origin":  "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    }
    if request.method == "OPTIONS":
        return web.Response(status=204, headers=headers)
    return web.Response(
        text=json.dumps(LATEST_DATA),
        content_type="application/json",
        headers=headers,
    )


async def run_web_server():
    """Run the aiohttp web server alongside the monitoring loop."""
    app = web.Application()
    app.router.add_get("/status",  status_handler)
    app.router.add_options("/status", status_handler)
    app.router.add_get("/health",  lambda _: web.Response(text="OK"))
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log("🌐 WEB", f"Status API listening on port {port}  →  /status")
    await asyncio.sleep(float("inf"))   # keep alive forever


# ─── Entry point ────────────────────────────────────────────────────────────

async def monitoring_loop(auth_state: dict):
    """Runs monitoring cycles while monitoring_active is True.
    Sleeps in short increments so /stop takes effect quickly."""
    global monitoring_active
    cycle = 0
    while True:
        if not monitoring_active:
            await asyncio.sleep(2)      # idle — wait for /start
            continue
        cycle += 1
        await run_cycle(auth_state, cycle)
        # Sleep in 2-second ticks so /stop is responsive
        for _ in range(INTERVAL // 2):
            if not monitoring_active:
                break
            await asyncio.sleep(2)


# ─── Telegram command polling ────────────────────────────────────────────────

async def tg_reply(session: aiohttp.ClientSession, chat_id, text: str):
    """Send a reply to a specific chat (used by command handler)."""
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        async with session.post(TG_API, json=payload) as resp:
            if resp.status != 200:
                log("TG CMD", f"Reply failed: {resp.status}")
    except Exception as e:
        log("TG CMD", f"Reply error: {e}")


async def telegram_command_loop():
    """Poll Telegram for /s and /f commands from the owner chat."""
    global monitoring_active, _last_update_id
    log("🤖 TG CMD", "Command listener started — send /s to run, /f to stop")
    async with aiohttp.ClientSession() as session:
        # ── Delete any stale webhook so getUpdates can receive messages ──
        try:
            del_url = f"https://api.telegram.org/bot{TG_TOKEN}/deleteWebhook?drop_pending_updates=true"
            async with session.get(del_url) as r:
                result = await r.json()
                if result.get("result"):
                    log("🤖 TG CMD", "Webhook deleted — long-polling active")
                else:
                    log("🤖 TG CMD", f"deleteWebhook: {result}")
        except Exception as e:
            log("🤖 TG CMD", f"Could not delete webhook: {e}")

        while True:
            try:
                params = {"timeout": 20, "offset": _last_update_id + 1}
                async with session.get(TG_UPDATES, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        await asyncio.sleep(5)
                        continue
                    data = await resp.json()
                    updates = data.get("result", [])
                    for update in updates:
                        _last_update_id = update["update_id"]
                        message = update.get("message") or update.get("channel_post", {})
                        if not message:
                            continue
                        chat_id = str(message.get("chat", {}).get("id", ""))
                        text    = message.get("text", "").strip().lower()

                        # Only accept commands from the authorised chat
                        if chat_id != TG_CHAT_ID:
                            continue

                        if text in ("/s", "/s@" + TG_TOKEN.split(":")[0]):
                            if monitoring_active:
                                await tg_reply(session, chat_id,
                                    "⚠️ <b>Monitor is already running.</b>\n"
                                    "Send /f to stop it.")
                            else:
                                monitoring_active = True
                                log("🤖 TG CMD", "/s received — monitoring RESUMED")
                                await tg_reply(session, chat_id,
                                    "✅ <b>Monitor STARTED</b>\n"
                                    f"<code>Interval: {INTERVAL}s</code>\n"
                                    "Send /f to stop.")

                        elif text in ("/f", "/f@" + TG_TOKEN.split(":")[0]):
                            if not monitoring_active:
                                await tg_reply(session, chat_id,
                                    "⚠️ <b>Monitor is already stopped.</b>\n"
                                    "Send /s to resume.")
                            else:
                                monitoring_active = False
                                log("🤖 TG CMD", "/f received — monitoring PAUSED")
                                await tg_reply(session, chat_id,
                                    "🛑 <b>Monitor STOPPED</b>\n"
                                    "Send /s to resume.")

                        elif text == "/status":
                            state = "🟢 RUNNING" if monitoring_active else "🔴 STOPPED"
                            cycle = LATEST_DATA.get("cycle", 0)
                            ts    = LATEST_DATA.get("timestamp") or "—"
                            await tg_reply(session, chat_id,
                                f"<b>▌ BOT STATUS</b>\n"
                                f"  Monitor  :  <b>{state}</b>\n"
                                f"  Cycle    :  <b>#{cycle}</b>\n"
                                f"  Last run :  <b>{ts}</b>")

            except asyncio.CancelledError:
                raise
            except Exception as e:
                log("TG CMD", f"Poll error: {e}")
                await asyncio.sleep(5)


async def main():
    global monitoring_active
    auth_token, device_id = login()
    save_opt, phone_auth  = build_payloads(device_id)

    # Shared mutable state — updated in-place on every re-login
    auth_state = {
        "headers":    build_headers(auth_token, device_id),
        "save_opt":   save_opt,
        "phone_auth": phone_auth,
    }

    # Start paused — user must send /start from Telegram
    monitoring_active = False
    log("🤖 BOT", "Send /start in Telegram to begin monitoring.")

    # Run monitoring loop, web server, and Telegram command listener concurrently
    await asyncio.gather(
        monitoring_loop(auth_state),
        run_web_server(),
        telegram_command_loop(),
    )


if __name__ == "__main__":
    asyncio.run(main())
