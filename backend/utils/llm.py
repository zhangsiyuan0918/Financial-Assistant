import json, os, requests, hashlib, time

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "llm_config.json")
_KEY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", ".llm_key")
_DEFAULT_URL = "https://api.deepseek.com"
_DEFAULT_MODEL = "deepseek-v4-flash"

# LLM 响应缓存
_llm_cache = {}
_CACHE_TTL = 300  # 5 分钟


def _get_cache_key(prompt, system_prompt):
    content = prompt + (system_prompt or "")
    return hashlib.md5(content.encode()).hexdigest()


def _get_fernet():
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
    try:
        with open(CONFIG_FILE, "rb") as f:
            data = f.read()
        if data[:5] == b"gAAAA":
            from cryptography.fernet import Fernet
            if os.path.exists(_KEY_FILE):
                with open(_KEY_FILE, "rb") as kf:
                    fernet = Fernet(kf.read())
                return json.loads(fernet.decrypt(data))
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

    # 检查缓存
    cache_key = _get_cache_key(prompt, system_prompt)
    if cache_key in _llm_cache:
        cached = _llm_cache[cache_key]
        if time.time() - cached["time"] < _CACHE_TTL:
            return cached["response"]

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
        response = data["choices"][0]["message"]["content"]
        # 存入缓存
        _llm_cache[cache_key] = {"response": response, "time": time.time()}
        # 清理过期缓存
        now = time.time()
        expired = [k for k, v in _llm_cache.items() if now - v["time"] > _CACHE_TTL]
        for k in expired:
            del _llm_cache[k]
        return response
    except Exception as e:
        return f"（LLM 查询失败：{str(e)}）"
