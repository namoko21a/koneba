import asyncio
import json
import time
import aiohttp

INTERVAL   = 30
TG_TOKEN   = "8889006993:AAEmCC3idYlvUK1hMP-c2Qtp_U2fGKVKQQo"
TG_CHAT_ID = "5295241896"
TG_API     = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"

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
    ts = time.strftime("%H:%M:%S")
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
            return tg, True
        except Exception:
            return f"<b>INDEX INFO</b>  [{status}]\n", False


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
            return tg, True
        except Exception:
            return f"<b>HOMEPAGE</b>  [{status}]\n", False


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
            return tg, True
        except Exception:
            return f"<b>PHONE ACCOUNTS</b>  [{status}]\n", False


def print_status_dashboard(cycle: int, statuses: dict):
    """Print a colour-coded KMPay status dashboard to the console."""
    OK  = "\033[92m●  OK    \033[0m"
    ERR = "\033[91m●  ERROR \033[0m"
    overall = all(statuses.values())
    banner  = "\033[92m  ✔  KMPay is WORKING\033[0m" if overall else "\033[91m  ✘  KMPay has ERRORS\033[0m"
    line    = "─" * 44
    print(f"\n  {line}")
    print(f"  {'KMPAY STATUS DASHBOARD':^42}")
    print(f"  Cycle #{cycle}  ·  {time.strftime('%Y-%m-%d %H:%M:%S')}")
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
        ts = time.strftime("%Y-%m-%d %H:%M:%S")

        # saveOpt & phoneAuth handle 406 internally and update auth_state
        (save_opt_sec, ok_save_opt)     = await call_save_opt(session, auth_state)
        (phone_auth_sec, ok_phone_auth) = await call_phone_auth(session, auth_state)

        # Refresh headers in case re-login happened
        headers = auth_state["headers"]

        (
            (index_sec, ok_index),
            (homepage_sec, ok_homepage),
            (phone_page_sec, ok_phone_page),
        ) = await asyncio.gather(
            call_index_info(session, auth_state),
            call_homepage(session, auth_state),
            call_phone_page(session, auth_state),
        )

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


async def main():
    auth_token, device_id = login()
    save_opt, phone_auth  = build_payloads(device_id)

    # Shared mutable state — updated in-place on every re-login
    auth_state = {
        "headers":    build_headers(auth_token, device_id),
        "save_opt":   save_opt,
        "phone_auth": phone_auth,
    }

    cycle = 0
    while True:
        cycle += 1
        await run_cycle(auth_state, cycle)
        await asyncio.sleep(INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
