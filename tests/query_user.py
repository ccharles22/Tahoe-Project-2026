from app import create_app
from app.extensions import db
from app.models import User

app = create_app()
with app.app_context():
    u = User.query.filter_by(username='integ_test_user').first()
    if not u:
        print('user not found')
    else:
        print('user found: id=', u.user_id, 'email=', u.email, 'pw_hash_len=', len(u.password_hash or ''))
