import bcrypt, os, json, secrets, time
from datetime import datetime, timedelta

AUTH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "auth.json")
TOKENS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "auth_tokens.json")

_tokens = {}  # token -> expiry (datetime)


def _load_auth():
    if os.path.exists(AUTH_FILE):
        with open(AUTH_FILE, "r") as f:
            return json.load(f)
    return {}


def _save_auth(data):
    os.makedirs(os.path.dirname(AUTH_FILE), exist_ok=True)
    with open(AUTH_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _save_tokens():
    os.makedirs(os.path.dirname(TOKENS_FILE), exist_ok=True)
    serializable = {t: exp.isoformat() for t, exp in _tokens.items()}
    with open(TOKENS_FILE, "w") as f:
        json.dump(serializable, f)


def _load_tokens():
    if os.path.exists(TOKENS_FILE):
        try:
            with open(TOKENS_FILE) as f:
                data = json.load(f)
            now = datetime.now()
            for t, exp_str in data.items():
                exp = datetime.fromisoformat(exp_str)
                if exp > now:
                    _tokens[t] = exp
        except (json.JSONDecodeError, ValueError):
            pass


# ---- Rate limiting ----

_login_attempts = {}  # ip -> (count, first_attempt_time)


def _check_rate_limit(ip, max_attempts=5, window=300):
    now = time.time()
    if ip in _login_attempts:
        count, first = _login_attempts[ip]
        if now - first > window:
            del _login_attempts[ip]
            return True
        if count >= max_attempts:
            return False
    return True


def _record_failed_attempt(ip):
    now = time.time()
    if ip in _login_attempts:
        count, first = _login_attempts[ip]
        _login_attempts[ip] = (count + 1, first)
    else:
        _login_attempts[ip] = (1, now)


def _clear_attempts(ip):
    _login_attempts.pop(ip, None)


# ---- Password ----

def init_password(password):
    h = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    _save_auth({"password_hash": h.decode("utf-8")})


def verify_password(password):
    data = _load_auth()
    if not data:
        return True  # No password configured — allow access (first-time setup)
    stored = data.get("password_hash", "")
    if not stored:
        return True
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
    except Exception:
        return False


# ---- Login / Token ----

def login(password, ip="unknown"):
    if not _check_rate_limit(ip):
        return None, "登录过于频繁，请5分钟后重试"
    if not verify_password(password):
        _record_failed_attempt(ip)
        return None, "密码错误"
    _clear_attempts(ip)
    token = secrets.token_hex(32)
    _tokens[token] = datetime.now() + timedelta(hours=24)
    _save_tokens()
    return token, None


def check_token(token):
    expiry = _tokens.get(token)
    if not expiry:
        return False
    if datetime.now() > expiry:
        del _tokens[token]
        _save_tokens()
        return False
    return True


def require_auth():
    """如果配置了密码但未认证，返回 'unauthorized'；否则 None"""
    data = _load_auth()
    if not data:
        return None
    return "unauthorized"


# Load persisted tokens on import
_load_tokens()
