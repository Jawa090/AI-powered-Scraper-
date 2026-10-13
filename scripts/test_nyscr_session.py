import subprocess
import os
import sys
import time
import urllib.request
import json

chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
profile_path = os.path.abspath(".nyscr-browser-profile")

print(f"Starting Chrome with profile {profile_path}...")
proc = subprocess.Popen([
    chrome_path,
    "--remote-debugging-port=9222",
    "--remote-debugging-address=127.0.0.1",
    f"--user-data-dir={profile_path}",
    "--headless=new",
    "--no-first-run",
    "--no-default-browser-check",
    "https://www.nyscr.ny.gov/Account/Login"
])

try:
    for i in range(15):
        try:
            with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=2) as resp:
                break
        except Exception:
            time.sleep(1)
    else:
        print("Could not connect to debugger port 9222.")
        sys.exit(1)

    sys.path.append(os.path.abspath('Backend'))
    from settings import settings
    settings.NYSCR_DEBUGGER_ADDRESS = '127.0.0.1:9222'
    from scrappers.nyscr import NyscrScraper
    scraper = NyscrScraper(headless=False)
    ready = scraper.setup_chrome()
    print("setup_chrome returned:", ready)
    if ready:
        try:
            print("Attempting login...")
            res = scraper.login()
            print("Login returned:", res)
        except Exception as e:
            print("Login raised exception:", type(e).__name__, e)
            print("Current URL:", scraper.driver.current_url)
            print("Page body excerpt:", scraper.driver.find_element("tag name", "body").text[:500])
        scraper.close()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    print("Cleaned up Chrome process.")
