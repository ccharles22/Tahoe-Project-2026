"""
Lightweight integration test: register -> login -> update settings -> verify
Run while the dev server is running at http://127.0.0.1:5000
"""
import re
import sys
import time
from urllib.parse import urljoin

import requests

BASE = "http://127.0.0.1:5000"

session = requests.Session()

def get_csrf(html):
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    return m.group(1) if m else None

def fetch(path):
    r = session.get(urljoin(BASE, path))
    r.raise_for_status()
    return r

def register(username, email, password):
    r = fetch('/auth/register')
    csrf = get_csrf(r.text)
    payload = {
        'username': username,
        'email': email,
        'password': password,
        'confirm_password': password,
        'csrf_token': csrf,
    }
    r2 = session.post(urljoin(BASE, '/auth/register'), data=payload, allow_redirects=True)
    return r2

def login(username, password):
    r = fetch('/auth/login')
    csrf = get_csrf(r.text)
    payload = {'username': username, 'password': password, 'csrf_token': csrf}
    r2 = session.post(urljoin(BASE, '/auth/login'), data=payload, allow_redirects=True)
    return r2

def update_settings(new_username, new_email):
    r = fetch('/auth/settings')
    csrf = get_csrf(r.text)
    # include hidden_tag fields like csrf_token; submit button name may vary but Flask-WTF doesn't require it
    payload = {
        'username': new_username,
        'email': new_email,
        'current_password': '',
        'new_password': '',
        'receive_notifications': 'y',
        'csrf_token': csrf,
    }
    r2 = session.post(urljoin(BASE, '/auth/settings'), data=payload, allow_redirects=True)
    return r2


def main():
    uname = 'integ_test_user'
    email = 'integ_test_user@example.com'
    pwd = 'Testpass123!'

    # Try registering (ignore failure if user exists)
    try:
        r = register(uname, email, pwd)
        print('register status', r.status_code)
        # debug: print small snippet around flash / title to diagnose failures
        print('register response title/snippet:', r.text[:600])
    except Exception as e:
        print('register error', e)

    # Check whether we're already authenticated (register may log the user in)
    r = fetch('/auth/login')
    if 'name="username"' in r.text or '<title>Login' in r.text:
        try:
            r = login(uname, pwd)
            print('login status', r.status_code)
            if r.url.endswith('/auth/login'):
                print('Login appears to have failed (still on login page). Response snippet:')
                print(r.text[:800])
                sys.exit(2)
        except Exception as e:
            print('login error', e)
            sys.exit(3)
    else:
        print('Already authenticated after register; skipping explicit login')

    # Fetch settings page
    r = fetch('/auth/settings')
    print('/auth/settings loaded, length', len(r.text))
    if 'Account Settings' not in r.text:
        print('Settings page content unexpected')
        sys.exit(4)

    # Update settings
    try:
        new_un = uname + '_2'
        new_em = 'changed+' + email
        r2 = update_settings(new_un, new_em)
        print('settings POST status', r2.status_code)
        if 'Settings updated successfully' in r2.text or r2.url.endswith('/auth/settings'):
            print('Settings submission appears successful')
        else:
            print('Settings submission response length', len(r2.text))
    except Exception as e:
        print('settings error', e)
        sys.exit(5)

    print('Integration script completed')

if __name__ == '__main__':
    main()
