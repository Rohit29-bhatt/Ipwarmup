"""
automation.py — Real Playwright browser automation for IP warmup.
Each provider (Gmail, Outlook, Yahoo, etc.) has its own login + search + click flow.
"""

import time
import random
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout


def warm_account(acc, subject, config, log):
    """
    Entry point called by app.py for each account.
    Returns result dict: {status, login, found, clicks, in_spam, note, links, screenshot}
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=config.get('headless', True),
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
        )
        context = browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            ),
            viewport={'width': 1280, 'height': 800},
        )
        page = context.new_page()
        page.set_default_timeout(30000)

        provider_type = acc.get('type', 'custom')
        result = {
            'status': 'fail', 'login': False, 'found': False,
            'clicks': 0, 'in_spam': False, 'note': '', 'links': [], 'screenshot': None
        }

        try:
            if provider_type == 'gmail':
                result = handle_gmail(page, acc, subject, config, log)
            elif provider_type == 'outlook':
                result = handle_outlook(page, acc, subject, config, log)
            elif provider_type == 'yahoo':
                result = handle_yahoo(page, acc, subject, config, log)
            elif provider_type == 'proton':
                result = handle_proton(page, acc, subject, config, log)
            else:
                result = handle_generic_imap(page, acc, subject, config, log)
        except Exception as e:
            log(f'✗ Unexpected error: {e}', 'error')
            result['note'] = str(e)
        finally:
            browser.close()

        return result


# ─── Human-like helpers ──────────────────────────────────────────────────────

def human_type(page, selector, text):
    """Type text character by character with random delays."""
    page.click(selector)
    for ch in text:
        page.keyboard.type(ch, delay=random.randint(40, 120))
    time.sleep(random.uniform(0.3, 0.7))


def human_delay(min_s=0.5, max_s=1.5):
    time.sleep(random.uniform(min_s, max_s))


def click_links_in_email(page, min_clicks, log):
    """
    Opens all links inside the email body iframe or container,
    clicks at least min_clicks of them in new tabs, then closes them.
    Returns list of clicked URLs.
    """
    clicked = []
    try:
        # Try to find links in iframe (Gmail) or direct container
        frames = page.frames
        target_frame = next(
            (f for f in frames if f != page.main_frame and f.url not in ('about:blank', '')),
            page.main_frame
        )
        links = target_frame.query_selector_all('a[href]')
        clickable = [
            l for l in links
            if l.get_attribute('href') and
               l.get_attribute('href').startswith('http') and
               'unsubscribe' not in (l.get_attribute('href') or '').lower() and
               'unsubscribe' not in (l.inner_text() or '').lower()
        ]
        random.shuffle(clickable)
        to_click = clickable[:max(min_clicks, min(min_clicks + 2, len(clickable)))]

        for i, link in enumerate(to_click):
            try:
                href = link.get_attribute('href')
                # Open in new tab
                with page.context.expect_page() as new_page_info:
                    link.click(modifiers=['Control'])
                new_page = new_page_info.value
                new_page.wait_for_load_state('domcontentloaded', timeout=10000)
                human_delay(1.0, 2.5)
                new_page.close()
                clicked.append(href)
                log(f'✓ Clicked link {i+1}: {href[:60]}…', 'success')
            except Exception as e:
                log(f'⚠ Link {i+1} click failed: {e}', 'warn')
    except Exception as e:
        log(f'⚠ Link extraction error: {e}', 'warn')
    return clicked


# ─── Gmail ───────────────────────────────────────────────────────────────────

def handle_gmail(page, acc, subject, config, log):
    result = {'status': 'fail', 'login': False, 'found': False,
              'clicks': 0, 'in_spam': False, 'note': '', 'links': [], 'screenshot': None}
    try:
        log('→ Navigating to Gmail…', 'info')
        page.goto('https://accounts.google.com/signin/v2/identifier?service=mail', wait_until='networkidle')
        human_delay()

        # Enter email
        human_type(page, 'input[type="email"]', acc['email'])
        page.click('#identifierNext')
        page.wait_for_selector('input[type="password"]', timeout=15000)
        human_delay(0.8, 1.5)

        # Enter password
        human_type(page, 'input[type="password"]', acc['password'])
        page.click('#passwordNext')

        # Wait for Gmail inbox
        try:
            page.wait_for_url('**/mail.google.com/**', timeout=20000)
            human_delay(2, 3)
            log('✓ Logged in to Gmail', 'success')
            result['login'] = True
        except PWTimeout:
            log('✗ Login failed — check credentials or 2FA prompt', 'error')
            result['note'] = 'Login failed — invalid credentials or 2FA'
            return result

        # Search for subject
        folder = config.get('folder', 'inbox')
        search_query = f'subject:"{subject}"'
        if folder == 'spam':
            search_query += ' in:spam'
        elif folder == 'promotions':
            search_query += ' category:promotions'
        elif folder == 'all':
            search_query += ' in:anywhere'

        log(f'→ Searching: {search_query}', 'info')
        search_box = page.wait_for_selector('input[aria-label="Search mail"]', timeout=10000)
        search_box.click()
        human_delay(0.3, 0.6)
        page.keyboard.type(search_query)
        page.keyboard.press('Enter')
        page.wait_for_load_state('networkidle')
        human_delay(1.5, 2.5)

        # Check if email found
        no_results = page.query_selector('td.TC')
        if no_results:
            log(f'✗ Email not found — subject: "{subject}"', 'error')
            result['note'] = f'Email not found in {folder}'
            result['status'] = 'partial'
            return result

        # Check for spam
        in_spam = False
        try:
            spam_badge = page.query_selector('[data-tooltip="Spam"]')
            if spam_badge:
                in_spam = True
                log('⚠ Email is in spam folder', 'warn')
                if config.get('move_from_spam'):
                    page.click('[data-tooltip="Not spam"]')
                    human_delay(1, 2)
                    log('→ Marked as Not Spam, moved to inbox', 'info')
        except Exception:
            pass

        result['found'] = True
        result['in_spam'] = in_spam
        log('✓ Email found — opening…', 'success')

        # Click first result
        first_row = page.query_selector('tr.zA')
        if first_row:
            first_row.click()
            page.wait_for_load_state('networkidle')
            human_delay(1.5, 2.5)

        # Click links
        links = click_links_in_email(page, config['min_clicks'], log)
        result['links']  = links
        result['clicks'] = len(links)
        result['status'] = 'success' if len(links) >= config['min_clicks'] else 'partial'
        result['note']   = 'Moved from spam' if in_spam and config.get('move_from_spam') else ('In spam' if in_spam else 'Inbox')

    except Exception as e:
        log(f'✗ Gmail error: {e}', 'error')
        result['note'] = str(e)
    return result


# ─── Outlook ─────────────────────────────────────────────────────────────────

def handle_outlook(page, acc, subject, config, log):
    result = {'status': 'fail', 'login': False, 'found': False,
              'clicks': 0, 'in_spam': False, 'note': '', 'links': [], 'screenshot': None}
    try:
        log('→ Navigating to Outlook…', 'info')
        page.goto('https://outlook.live.com/owa/', wait_until='networkidle')
        human_delay()

        page.click('a[data-task="signin"]', timeout=10000)
        page.wait_for_selector('input[type="email"]', timeout=15000)
        human_type(page, 'input[type="email"]', acc['email'])
        page.click('input[type="submit"]')
        page.wait_for_selector('input[type="password"]', timeout=15000)
        human_delay(0.8, 1.2)
        human_type(page, 'input[type="password"]', acc['password'])
        page.click('input[type="submit"]')

        try:
            # Handle "Stay signed in?" prompt
            stay_btn = page.wait_for_selector('input[id="idBtn_Back"]', timeout=5000)
            stay_btn.click()
        except Exception:
            pass

        try:
            page.wait_for_url('**/outlook.live.com/mail/**', timeout=20000)
            human_delay(2, 3)
            log('✓ Logged in to Outlook', 'success')
            result['login'] = True
        except PWTimeout:
            log('✗ Login failed', 'error')
            result['note'] = 'Login failed'
            return result

        # Search
        log(f'→ Searching for subject: "{subject}"', 'info')
        search = page.wait_for_selector('input[aria-label="Search"]', timeout=10000)
        search.click()
        page.keyboard.type(f'subject:{subject}')
        page.keyboard.press('Enter')
        page.wait_for_load_state('networkidle')
        human_delay(2, 3)

        # Check results
        items = page.query_selector_all('[role="option"]')
        if not items:
            log(f'✗ Email not found — subject: "{subject}"', 'error')
            result['note'] = 'Email not found'
            result['status'] = 'partial'
            return result

        result['found'] = True
        log('✓ Email found — opening…', 'success')
        items[0].click()
        page.wait_for_load_state('networkidle')
        human_delay(1.5, 2.5)

        links = click_links_in_email(page, config['min_clicks'], log)
        result['links']  = links
        result['clicks'] = len(links)
        result['status'] = 'success' if len(links) >= config['min_clicks'] else 'partial'
        result['note']   = 'Inbox'

    except Exception as e:
        log(f'✗ Outlook error: {e}', 'error')
        result['note'] = str(e)
    return result


# ─── Yahoo Mail ──────────────────────────────────────────────────────────────

def handle_yahoo(page, acc, subject, config, log):
    result = {'status': 'fail', 'login': False, 'found': False,
              'clicks': 0, 'in_spam': False, 'note': '', 'links': [], 'screenshot': None}
    try:
        log('→ Navigating to Yahoo Mail…', 'info')
        page.goto('https://login.yahoo.com/', wait_until='networkidle')
        human_delay()

        human_type(page, 'input#login-username', acc['email'])
        page.click('input#login-signin')
        page.wait_for_selector('input#login-passwd', timeout=15000)
        human_delay(0.8, 1.2)
        human_type(page, 'input#login-passwd', acc['password'])
        page.click('button#login-signin')

        try:
            page.wait_for_url('**/mail.yahoo.com/**', timeout=20000)
            human_delay(2, 3)
            log('✓ Logged in to Yahoo Mail', 'success')
            result['login'] = True
        except PWTimeout:
            log('✗ Login failed', 'error')
            result['note'] = 'Login failed'
            return result

        log(f'→ Searching for subject: "{subject}"', 'info')
        search = page.wait_for_selector('input[placeholder="Search email"]', timeout=10000)
        search.click()
        page.keyboard.type(subject)
        page.keyboard.press('Enter')
        page.wait_for_load_state('networkidle')
        human_delay(2, 3)

        items = page.query_selector_all('a.C_B')
        if not items:
            items = page.query_selector_all('[data-test-id="message-list-item"]')
        if not items:
            log(f'✗ Email not found — subject: "{subject}"', 'error')
            result['note'] = 'Email not found'
            result['status'] = 'partial'
            return result

        result['found'] = True
        log('✓ Email found — opening…', 'success')
        items[0].click()
        page.wait_for_load_state('networkidle')
        human_delay(1.5, 2.5)

        links = click_links_in_email(page, config['min_clicks'], log)
        result['links']  = links
        result['clicks'] = len(links)
        result['status'] = 'success' if len(links) >= config['min_clicks'] else 'partial'
        result['note']   = 'Inbox'

    except Exception as e:
        log(f'✗ Yahoo error: {e}', 'error')
        result['note'] = str(e)
    return result


# ─── ProtonMail ──────────────────────────────────────────────────────────────

def handle_proton(page, acc, subject, config, log):
    result = {'status': 'fail', 'login': False, 'found': False,
              'clicks': 0, 'in_spam': False, 'note': '', 'links': [], 'screenshot': None}
    try:
        log('→ Navigating to ProtonMail…', 'info')
        page.goto('https://account.proton.me/login', wait_until='networkidle')
        human_delay(1, 2)

        human_type(page, 'input#username', acc['email'])
        human_type(page, 'input#password', acc['password'])
        page.click('button[type="submit"]')

        try:
            page.wait_for_url('**/mail.proton.me/**', timeout=25000)
            human_delay(2, 4)
            log('✓ Logged in to ProtonMail', 'success')
            result['login'] = True
        except PWTimeout:
            log('✗ Login failed', 'error')
            result['note'] = 'Login failed'
            return result

        log(f'→ Searching for subject: "{subject}"', 'info')
        search = page.wait_for_selector('input[placeholder="Search messages"]', timeout=10000)
        search.click()
        page.keyboard.type(subject)
        page.keyboard.press('Enter')
        page.wait_for_load_state('networkidle')
        human_delay(2, 3)

        items = page.query_selector_all('[data-shortcut-target="item-container"]')
        if not items:
            log(f'✗ Email not found — subject: "{subject}"', 'error')
            result['note'] = 'Email not found'
            result['status'] = 'partial'
            return result

        result['found'] = True
        log('✓ Email found — opening…', 'success')
        items[0].click()
        page.wait_for_load_state('networkidle')
        human_delay(1.5, 2.5)

        links = click_links_in_email(page, config['min_clicks'], log)
        result['links']  = links
        result['clicks'] = len(links)
        result['status'] = 'success' if len(links) >= config['min_clicks'] else 'partial'
        result['note']   = 'Inbox'

    except Exception as e:
        log(f'✗ ProtonMail error: {e}', 'error')
        result['note'] = str(e)
    return result


# ─── Generic / Corporate (webmail fallback) ───────────────────────────────────

def handle_generic_imap(page, acc, subject, config, log):
    """
    For corporate domains — tries common webmail URLs.
    Falls back to simulation if none are reachable.
    """
    result = {'status': 'fail', 'login': False, 'found': False,
              'clicks': 0, 'in_spam': False, 'note': '', 'links': [], 'screenshot': None}
    domain = acc.get('domain', '')
    candidates = [
        f'https://mail.{domain}',
        f'https://webmail.{domain}',
        f'https://outlook.{domain}',
        f'https://{domain}/mail',
    ]
    log(f'→ Corporate domain — trying webmail URLs for {domain}', 'info')
    for url in candidates:
        try:
            resp = page.goto(url, wait_until='domcontentloaded', timeout=10000)
            if resp and resp.status < 400:
                log(f'→ Reached: {url}', 'info')
                human_delay(1, 2)
                # Generic: try to fill first email + password fields
                try:
                    human_type(page, 'input[type="email"], input[name="email"], input[name="username"]', acc['email'])
                    human_type(page, 'input[type="password"]', acc['password'])
                    page.click('button[type="submit"], input[type="submit"]')
                    human_delay(2, 3)
                    log('✓ Submitted login form', 'success')
                    result['login'] = True
                    result['note'] = f'Generic login at {url}'
                    result['status'] = 'partial'
                except Exception as fe:
                    log(f'⚠ Form fill failed: {fe}', 'warn')
                break
        except Exception:
            continue

    if not result['login']:
        log('✗ Could not reach any webmail URL for this domain', 'error')
        result['note'] = f'No reachable webmail found for {domain}'
    return result
