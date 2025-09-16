from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
from datetime import datetime, timedelta
from dotenv import load_dotenv
import logging
import os
import re
import sys

load_dotenv()

# ---------- Logging setup ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        # uncomment next line if you want a log file too
        # logging.FileHandler("automation.log", encoding="utf-8")
    ],
)

# ---------- Config ----------
URL = os.getenv("URL")
COMPANY_ID = os.getenv("COMPANY_ID")
USERNAME   = os.getenv("USERNAME")
PASSWORD   = os.getenv("PASSWORD")

DOWNLOAD_DIR = "./downloads"
TIMEOUT = 15000  # default timeout for waits in ms


def compute_tomorrow_mmddyyyy() -> str:
    """Return tomorrow's date in mm/dd/yyyy format."""
    return (datetime.now() + timedelta(days=1)).strftime("%m/%d/%Y")


def main():
    with sync_playwright() as p:
        # Launch Chromium (visible so you can watch the flow)
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            # 1) Navigate to login
            logging.info("STEP 1: Opening portal", URL)
            page.goto(URL, wait_until="domcontentloaded", timeout=TIMEOUT)

            # Login form
            logging.info("STEP 2: Filling company/user and submitting...")
            page.locator("#company").wait_for(state="visible", timeout=TIMEOUT)
            page.fill("#company", COMPANY_ID)
            page.fill("#user", USERNAME)
            page.click("#login")

            logging.info("STEP 3: Entering password...")
            page.locator("#passwordPrompt").wait_for(state="visible", timeout=TIMEOUT)
            page.fill("#passwordPrompt", PASSWORD)
            page.click("#login")

            # 4) Dashboard
            logging.info("STEP 4: Waiting for Dashboard menu...")
            page.locator("#menu-DASHBOARD").wait_for(state="visible", timeout=TIMEOUT)
            page.click("#menu-DASHBOARD")

            # 5) Payments & Transfers -> Payment Activity
            logging.info("STEP 5: Opening 'Payments & Transfers' -> 'Payment Activity'...")
            page.locator('//a[span[text()="Payments & Transfers"]]').wait_for(
                state="visible", timeout=TIMEOUT
            )
            page.click('//a[span[text()="Payments & Transfers"]]')
            page.get_by_text("Payment Activity", exact=True).click()

            # 6) Payment History from sidebar
            logging.info("STEP 6: Opening 'Payment History' in sidebar...")
            page.locator("#menu-PAYMENTACTIVITY-pastActivity").wait_for(
                state="visible", timeout=TIMEOUT
            )
            page.click("#menu-PAYMENTACTIVITY-pastActivity")

            # 7) ACH Payments tab
            logging.info("STEP 7: Switching to 'ACH Payments' tab...")
            try:
                page.locator("#ui-id-3").wait_for(state="visible", timeout=10000)
                page.click("#ui-id-3")
            except PWTimeoutError:
                logging.info("...ID not found, using role-based tab selector")
                page.get_by_role("tab", name=re.compile(r"ACH Payments", re.I)).click()

            # Scope all subsequent actions to the visible ACH Payments tabpanel
            panel = page.get_by_role("tabpanel", name=re.compile(r"ACH Payments", re.I))

            # 8) Set From/To dates to tomorrow
            logging.info("STEP 8: Setting date range to tomorrow...")
            tomorrow = compute_tomorrow_mmddyyyy()

            from_box = panel.locator('input[name="datepicker_fromDate"]:visible').first
            to_box   = panel.locator('input[name="datepicker_toDate"]:visible').first

            from_box.wait_for(state="visible", timeout=TIMEOUT)
            to_box.wait_for(state="visible", timeout=TIMEOUT)

            # Make sure they’re in view and fill
            from_box.scroll_into_view_if_needed()
            to_box.scroll_into_view_if_needed()
            from_box.fill(tomorrow)
            to_box.fill(tomorrow)

            # Fire change events if the UI listens for them
            from_box.dispatch_event("change")
            to_box.dispatch_event("change")

            # logging.info("Set to %s", tomorrow)

            # 9) Click Search
            logging.info("STEP 9: Clicking 'Search'...")
            panel.get_by_role("button", name="Search").click()

            # 10) Open Export split-button menu (right-hand arrow)
            logging.info("STEP 10: Opening Export split-button menu (arrow)...")
            panel.locator("button.splitbutton-right.menubutton:visible").first.click()

            # 11) Choose 'Summary and Details with Additional Information'
            logging.info("STEP 11: Selecting 'Summary and Details with Additional Information'...")
            page.get_by_role(
                "button",
                name=re.compile(r"Summary and Details\s*with Additional Information", re.I),
            ).click()

            # 12) Download
            logging.info("STEP 12: Waiting for 'Download' button and downloading file...")
            page.locator("button:has-text('Download')").first.wait_for(
                state="visible", timeout=TIMEOUT
            )

            os.makedirs(DOWNLOAD_DIR, exist_ok=True)
            with page.expect_download() as download_info:
                page.locator("button:has-text('Download')").first.click()
            download = download_info.value

            suggested = download.suggested_filename or "export_file"
            filepath = os.path.join(DOWNLOAD_DIR, suggested)
            download.save_as(filepath)

            logging.info("Download detected: %s", suggested)
            logging.info("Saved to: %s", filepath)
            if os.path.exists(filepath):
                size = os.path.getsize(filepath)
                logging.info("File size: %s bytes", size)

            logging.info("ALL STEPS COMPLETED SUCCESSFULLY.")

            # Leave the page open briefly to inspect
            page.wait_for_timeout(3000)

        except Exception as e:
            logging.exception("FAILED: %s", e)
        finally:
            # Close resources
            try:
                context.close()
                browser.close()
            except Exception:
                pass
            logging.info("Done.")


if __name__ == "__main__":
    main()
