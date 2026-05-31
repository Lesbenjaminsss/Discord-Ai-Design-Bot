"""Tasarim botu ayarlari."""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

OWNER_ID = int(os.environ.get("BOT_OWNER_ID", "1324038081896251415"))

# OpenAI (May 2026+): dall-e-2/3 kaldirildi -> gpt-image-*
GPT_IMAGE_MODELS = (
    "gpt-image-1",
    "gpt-image-1-mini",
    "gpt-image-1.5",
    "gpt-image-2",
)
LEGACY_IMAGE_MODELS = ("dall-e-3", "dall-e-2")
ALL_IMAGE_MODELS = GPT_IMAGE_MODELS + LEGACY_IMAGE_MODELS

DEFAULT_IMAGE_MODEL = "gpt-image-1"

GPT_SIZES = {"1024x1024", "1024x1536", "1536x1024", "auto"}
DALLE3_SIZES = {"1024x1024", "1024x1792", "1792x1024"}
DALLE2_SIZES = {"256x256", "512x512", "1024x1024"}

GPT_QUALITIES = {"low", "medium", "high", "auto"}
DALLE3_QUALITIES = {"standard", "hd"}


def _clean(value: str) -> str:
    for ch in "\r\n\ufeff\u200b":
        value = value.replace(ch, "")
    value = value.strip().strip('"').strip("'")
    if value.lower().startswith("bot "):
        value = value[4:].strip()
    return value


def load_env_file() -> dict[str, str]:
    if not ENV_PATH.is_file():
        return {}
    for enc in ("utf-8-sig", "utf-8", "utf-16", "utf-16-le"):
        try:
            text = ENV_PATH.read_text(encoding=enc)
            break
        except UnicodeError:
            continue
    else:
        return {}

    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        out[key.strip().upper()] = _clean(val)
    return out


def get_token() -> str:
    env = load_env_file()
    return _clean(env.get("DISCORD_TOKEN", os.environ.get("DISCORD_TOKEN", "")))


def get_guild_id() -> str:
    env = load_env_file()
    return _clean(env.get("DISCORD_GUILD_ID", os.environ.get("DISCORD_GUILD_ID", "")))


def get_openai_api_key() -> str:
    env = load_env_file()
    return _clean(env.get("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY", "")))


def get_image_model() -> str:
    env = load_env_file()
    raw = env.get("IMAGE_MODEL", os.environ.get("IMAGE_MODEL", DEFAULT_IMAGE_MODEL))
    model = _clean(raw) or DEFAULT_IMAGE_MODEL
    if model in LEGACY_IMAGE_MODELS:
        return DEFAULT_IMAGE_MODEL
    if model in ALL_IMAGE_MODELS:
        return model
    return DEFAULT_IMAGE_MODEL


def is_gpt_image_model(model: str) -> bool:
    return model in GPT_IMAGE_MODELS or model.startswith("gpt-image-")


def get_image_size() -> str:
    env = load_env_file()
    raw = _clean(env.get("IMAGE_SIZE", os.environ.get("IMAGE_SIZE", "1024x1024")))
    return raw or "1024x1024"


def normalize_image_size(model: str, size: str) -> str | None:
    """Model icin gecerli boyut; bilinmeyen eski DALL-E boyutlarini donusturur."""
    if is_gpt_image_model(model):
        legacy_map = {
            "1024x1792": "1024x1536",
            "1792x1024": "1536x1024",
            "256x256": "1024x1024",
            "512x512": "1024x1024",
        }
        size = legacy_map.get(size, size)
        return size if size in GPT_SIZES else "1024x1024"
    if model == "dall-e-3":
        return size if size in DALLE3_SIZES else "1024x1024"
    if model == "dall-e-2":
        return size if size in DALLE2_SIZES else "1024x1024"
    return "1024x1024"


def get_image_quality() -> str:
    env = load_env_file()
    return _clean(env.get("IMAGE_QUALITY", os.environ.get("IMAGE_QUALITY", "medium")))


def normalize_image_quality(model: str, quality: str) -> str | None:
    if is_gpt_image_model(model):
        legacy_map = {"standard": "medium", "hd": "high"}
        quality = legacy_map.get(quality, quality)
        return quality if quality in GPT_QUALITIES else "auto"
    if model == "dall-e-3":
        q = quality if quality in DALLE3_QUALITIES else "standard"
        return q
    return None


def get_image_provider() -> str:
    """openai | pollinations | auto (OpenAI duserse ucretsiz yedek)."""
    env = load_env_file()
    raw = _clean(env.get("IMAGE_PROVIDER", os.environ.get("IMAGE_PROVIDER", "auto")))
    if raw in ("openai", "pollinations", "auto"):
        return raw
    return "auto"


def get_pollinations_model() -> str:
    env = load_env_file()
    return _clean(env.get("POLLINATIONS_MODEL", os.environ.get("POLLINATIONS_MODEL", "flux"))) or "flux"


def get_pollinations_api_key() -> str:
    env = load_env_file()
    return _clean(env.get("POLLINATIONS_API_KEY", os.environ.get("POLLINATIONS_API_KEY", "")))


def parse_width_height(size: str) -> tuple[int, int]:
    if "x" in size:
        parts = size.split("x", 1)
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            pass
    return 1024, 1024


def get_tasarla_cooldown_sec() -> int:
    env = load_env_file()
    raw = _clean(env.get("TASARLA_COOLDOWN_SEC", os.environ.get("TASARLA_COOLDOWN_SEC", "45")))
    try:
        return max(0, int(raw))
    except ValueError:
        return 45


def check_token(token: str) -> tuple[bool, str]:
    if not token:
        return False, "Token bos — .env dosyasinda DISCORD_TOKEN=... olmali"
    req = urllib.request.Request(
        "https://discord.com/api/v10/users/@me",
        headers={
            "Authorization": f"Bot {token}",
            "User-Agent": "DiscordBot (https://github.com/discord/discord-api-docs)",

        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            return True, f"Token gecerli (@{data.get('username', '?')})"
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "Token gecersiz (401). Bot -> Reset Token, .env guncelle."
        return False, f"Discord API hata: {e.code}"
    except Exception as e:
        return False, f"Baglanti hatasi: {e}"
