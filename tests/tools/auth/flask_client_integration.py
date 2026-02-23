from app import create_app

app = create_app()
app.testing = True
# Disable CSRF for test client convenience
app.config['WTF_CSRF_ENABLED'] = False

with app.test_client() as c:
    # register
    rv = c.get('/auth/register')
    print('GET register', rv.status_code)
    rv = c.post('/auth/register', data={'username':'cli_user','email':'cli_user@example.com','password':'CliPass123!'}, follow_redirects=True)
    print('POST register', rv.status_code)

    # login
    rv = c.get('/auth/login')
    print('GET login', rv.status_code)
    rv = c.post('/auth/login', data={'username':'cli_user','password':'CliPass123!'}, follow_redirects=True)
    print('POST login', rv.status_code)
    if b'Invalid username or password' in rv.data:
        print('login failed (client)')
    else:
        print('login ok (client)')

    # get settings
    rv = c.get('/auth/settings')
    print('/auth/settings', rv.status_code)
    if b'Account Settings' in rv.data:
        print('settings page found')

    # post settings change
    rv = c.post('/auth/settings', data={'username':'cli_user2','email':'cli_user2@example.com','current_password':'','new_password':''}, follow_redirects=True)
    print('POST settings', rv.status_code)
    if b'Settings updated successfully' in rv.data:
        print('settings saved')
    else:
        print('settings response len', len(rv.data))
