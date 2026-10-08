from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional, TypeVar
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options

from settings import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


def get_chrome_options(headless: bool = True) -> Options:
    """Build Chrome options with anti-bot evasion and stability flags."""
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return options


def make_driver(headless: bool = True, debugger_address: str | None = None) -> webdriver.Remote | webdriver.Chrome:
    """
    Factory function creating a configured Selenium WebDriver.

    Uses settings.SELENIUM_MODE ('local' or 'remote'):
    - 'remote': connects to standalone Chrome grid at settings.SELENIUM_REMOTE_URL
    - 'local': creates local Chrome instance using Selenium Manager (no webdriver-manager)
    """
    options = Options() if debugger_address else get_chrome_options(headless=headless)
    if debugger_address:
        options.debugger_address = debugger_address

    mode = settings.SELENIUM_MODE.lower() if settings.SELENIUM_MODE else "local"

    if debugger_address and mode != 'local':
        raise ValueError('An existing debugging browser requires SELENIUM_MODE=local.')
    if mode == "remote":
        remote_url = settings.SELENIUM_REMOTE_URL
        if not remote_url:
            raise ValueError("SELENIUM_MODE is 'remote' but SELENIUM_REMOTE_URL is not set.")
        logger.info("Connecting to remote Selenium instance at %s", remote_url)
        driver = webdriver.Remote(command_executor=remote_url, options=options)
    else:
        logger.info("Launching local Chrome WebDriver (headless=%s)", headless)
        driver = webdriver.Chrome(options=options)

    # Configure anti-detection script injection
    if not debugger_address:
        try:
            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
            )
        except Exception as e:
            logger.debug("Failed to set CDP webdriver property: %s", e)

    # Enforce explicit timeouts
    driver.set_page_load_timeout(45)
    driver.set_script_timeout(30)

    return driver


from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

def wait_css(driver: WebDriver, css: str, timeout: int = 15) -> WebElement:
    """Wait for an element to be present and return it, or raise TimeoutException."""
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, css))
    )

def find_or_none(driver: WebDriver | WebElement, by: str, selector: str) -> Optional[WebElement]:
    """Find an element or return None immediately."""
    try:
        return driver.find_element(by, selector)
    except NoSuchElementException:
        return None



def retry_driver_call(
    func: Callable[[], T],
    *,
    max_retries: int = 3,
    delay: float = 1.0,
    action_name: str = "driver action",
) -> T:
    """Execute a WebDriver callable with bounded same-call retries on transient errors."""
    last_err: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except WebDriverException as e:
            last_err = e
            if attempt == max_retries:
                logger.error(
                    "WebDriver call failed for '%s' after %d attempts: %s",
                    action_name,
                    attempt,
                    e,
                )
                raise
            logger.warning(
                "Transient WebDriver failure for '%s' (attempt %d/%d): %s. Retrying in %.1fs...",
                action_name,
                attempt,
                max_retries,
                e,
                delay,
            )
            time.sleep(delay)
    if last_err:
        raise last_err
    raise RuntimeError(f"Unexpected exit in retry_driver_call for {action_name}")
