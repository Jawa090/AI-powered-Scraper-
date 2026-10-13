import sys, os, time
sys.path.append(os.path.abspath('Backend'))
from settings import settings
settings.NYSCR_DEBUGGER_ADDRESS = ""
settings.SELENIUM_MODE = 'local'
from scrappers.driver import make_driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

driver = make_driver(headless=True)
try:
    print("Navigating to NYSCR login...")
    driver.get("https://www.nyscr.ny.gov/Account/Login")
    time.sleep(3)
    
    token = driver.execute_script("return document.getElementById('g-recaptcha-response-1') ? document.getElementById('g-recaptcha-response-1').value : null;")
    print("reCAPTCHA token on load:", token[:30] if token else "None")
    
    if not token:
        print("Waiting for grecaptcha...")
        token = driver.execute_script("""
            var done = arguments[0];
            if (typeof grecaptcha !== 'undefined' && grecaptcha.execute) {
                grecaptcha.execute('6LchipYnAAAAACPFYsm9gAiKVbENM-o6E5WQt7tU', {action: 'homepage'}).then(function(t) {
                    done(t);
                }).catch(function(e) {
                    done('ERROR: ' + e);
                });
            } else {
                done('NO_GRECAPTCHA');
            }
        """)
        print("Explicit execute token:", token[:30] if token else "None")

    user_field = driver.find_element(By.ID, "Username")
    pass_field = driver.find_element(By.ID, "Password")
    user_field.clear()
    user_field.send_keys("Johnwood123")
    pass_field.clear()
    pass_field.send_keys("Rush@123456789")
    
    # check recaptcha token again
    token_now = driver.execute_script("return document.getElementById('g-recaptcha-response-1') ? document.getElementById('g-recaptcha-response-1').value : null;")
    print("reCAPTCHA token before click:", token_now[:30] if token_now else "None")

    submit = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
    submit.click()
    time.sleep(4)
    print("URL after submit:", driver.current_url)
    
    body = driver.find_element(By.TAG_NAME, "body").text
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    for l in lines[:20]:
        print("BODY:", l)

finally:
    driver.quit()
