import secrets
import string


def generate_code(prefix='BM', length=12):
    alphabet = string.ascii_uppercase + string.digits
    body = ''.join(secrets.choice(alphabet) for _ in range(length))
    return f'{prefix}-{body}'
