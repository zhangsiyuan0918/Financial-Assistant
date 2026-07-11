import json, os, requests

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "llm_config.json")
_KEY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", ".llm_key")
_DEFAULT_URL = "https://api.deepseek.com"
_DEFAULT_MODEL = "deepseek-v4-flash"


def _get_fernet():
    """Get or create a Fernet instance for encrypting LLM config."""
    from cryptography.fernet import Fernet
    os.makedirs(os.path.dirname(_KEY_FILE), exist_ok=True)
    if os.path.exists(_KEY_FILE):
        with open(_KEY_FILE, "rb") as f:
            return Fernet(f.read())
    key = Fernet.generate_key()
    with open(_KEY_FILE, "wb") as f:
        f.write(key)
    return Fernet(key)


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    # Try encrypted format first
    try:
        with open(CONFIG_FILE, "rb") as f:
            data = f.read()
        if data[:5] == b"gAAAA":  # Fernet token prefix
            from cryptography.fernet import Fernet
            key_path = _KEY_FILE
            if os.path.exists(key_path):
                with open(key_path, "rb") as kf:
                    fernet = Fernet(kf.read())
                return json.loads(fernet.decrypt(data))
        # Legacy plaintext
        return json.loads(data.decode("utf-8"))
    except Exception:
        return {}


def save_config(data):
    try:
        fernet = _get_fernet()
        encrypted = fernet.encrypt(json.dumps(data).encode("utf-8"))
        with open(CONFIG_FILE, "wb") as f:
            f.write(encrypted)
    except ImportError:
        # Fallback to plaintext if cryptography not installed
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)


def is_configured():
    cfg = load_config()
    return bool(cfg.get("api_key"))


def ask(prompt, system_prompt=None):
    cfg = load_config()
    api_key = cfg.get("api_key", "")
    base_url = cfg.get("base_url", _DEFAULT_URL)
    model = cfg.get("model", _DEFAULT_MODEL)
    if not api_key:
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        resp = requests.post(
            f"{base_url}/v1/chat/completions",
            headers=headers,
            json={"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 1024},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"（LLM 查询失败：{str(e)}）"
