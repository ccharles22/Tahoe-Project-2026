from app import create_app
from app.extensions import db, bcrypt
from app.models import User

app = create_app()
with app.app_context():
    u = User.query.filter_by(username='integ_test_user').first()
    if not u:
        print('no user')
    else:
        print('hash:', u.password_hash)
        ok = bcrypt.check_password_hash(u.password_hash, 'Testpass123!')
        print('bcrypt check:', ok)
