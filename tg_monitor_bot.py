import asyncio
import json
import time
import aiohttp

INTERVAL   = 50
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


async def call_save_opt(session: aiohttp.ClientSession, headers: dict, payload: dict) -> tuple:
    async with session.post(SAVE_OPT, data=json.dumps(payload), headers=headers) as resp:
        ok = resp.status == 200
        tg = f"  saveOpt      :  <b>ONLINE</b>  [{resp.status} OK]\n" if ok else f"  saveOpt      :  [{resp.status}]\n"
        return tg, ok


async def call_phone_auth(session: aiohttp.ClientSession, headers: dict, payload: dict) -> tuple:
    async with session.post(PHONE_AUTH, data=json.dumps(payload), headers=headers) as resp:
        ok = resp.status == 200
        tg = f"  phoneAuth    :  <b>ONLINE</b>  [{resp.status} OK]\n" if ok else f"  phoneAuth    :  [{resp.status}]\n"
        return tg, ok


async def call_index_info(session: aiohttp.ClientSession, headers: dict) -> tuple:
    async with session.get(INDEX_INFO, headers=headers) as resp:
        text = await resp.text()
        try:
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
            return f"<b>INDEX INFO</b>  [{resp.status}]\n"


async def call_homepage(session: aiohttp.ClientSession, headers: dict) -> tuple:
    async with session.post(HOMEPAGE, headers=headers) as resp:
        text = await resp.text()
        try:
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
            return f"<b>HOMEPAGE</b>  [{resp.status}]\n"


PHONE_PAGE_PAYLOAD = {
    "orderByType": "",
    "pageSize":    10,
    "orderBy":     "",
    "groupBy":     "",
    "pageNum":     1,
}


async def call_phone_page(session: aiohttp.ClientSession, headers: dict) -> tuple:
    async with session.post(PHONE_PAGE, data=json.dumps(PHONE_PAGE_PAYLOAD), headers=headers) as resp:
        text = await resp.text()
        try:
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
                status     = STATUS_MAP.get(raw_status, raw_status)
                day_income = float(item.get("dayIncome", 0))
                balance    = float(item.get("actualBalance", 0))
                rows += (
                    f"  📱 <b>{phone}</b>  [{bank}]\n"
                    f"     Status      :  <b>{status}</b>\n"
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
            return f"<b>PHONE ACCOUNTS</b>  [{resp.status}]\n"


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


async def run_cycle(headers: dict, save_opt_payload: dict, phone_auth_payload: dict, cycle: int):

    async with aiohttp.ClientSession() as session:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")

        (
            (save_opt_sec, ok_save_opt),
            (phone_auth_sec, ok_phone_auth),
            (index_sec, ok_index),
            (homepage_sec, ok_homepage),
            (phone_page_sec, ok_phone_page),
        ) = await asyncio.gather(
            call_save_opt(session, headers, save_opt_payload),
            call_phone_auth(session, headers, phone_auth_payload),
            call_index_info(session, headers),
            call_homepage(session, headers),
            call_phone_page(session, headers),
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
    headers            = build_headers(auth_token, device_id)
    save_opt, phone_auth = build_payloads(device_id)

    cycle = 0
    while True:
        cycle += 1
        await run_cycle(headers, save_opt, phone_auth, cycle)
        await asyncio.sleep(INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
