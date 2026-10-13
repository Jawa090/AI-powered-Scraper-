import sys, os, time
sys.path.append(os.path.abspath('Backend'))
from settings import settings
import requests
from bs4 import BeautifulSoup

def test_login(username, password):
    print(f"\n--- Testing login for {username} ---")
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    
    # Get login page
    r = session.get("https://www.nyscr.ny.gov/Account/Login")
    print("Login page status:", r.status_code)
    soup = BeautifulSoup(r.text, 'html.parser')
    token_input = soup.find('input', {'name': '__RequestVerificationToken'})
    token = token_input['value'] if token_input else None
    print("Verification token found:", bool(token))
    
    # Form data
    data = {
        '__RequestVerificationToken': token,
        'Username': username,
        'Password': password,
        'ReturnUrl': '',
        'Elevate': '',
        'g-recaptcha-response': ''
    }
    
    resp = session.post("https://www.nyscr.ny.gov/Account/Authenticate", data=data, allow_redirects=False)
    print("Authenticate status:", resp.status_code)
    print("Authenticate headers location:", resp.headers.get('Location'))
    print("Authenticate cookies:", dict(session.cookies))
    
    # If redirected, follow
    if resp.status_code in (301, 302, 303):
        loc = resp.headers.get('Location')
        if not loc.startswith('http'):
            loc = "https://www.nyscr.ny.gov" + loc
        r2 = session.get(loc)
        print("Redirected to:", r2.url)
        print("Is login in redirected url?:", "login" in r2.url.lower())
        print("Logged in text in page?:", any(w in r2.text.lower() for w in ["log off", "logout", "welcome", "my account"]))
    else:
        soup2 = BeautifulSoup(resp.text, 'html.parser')
        errors = [e.get_text(strip=True) for e in soup2.select('.text-danger, .validation-summary-errors')]
        print("Form errors:", [e for e in errors if e])

test_login("Johnwood123", "Rush@123456789")
test_login("kody2143", "TTHg6n*C7KuMES*")
