"""Gorsel uretimi: OpenAI GPT Image veya Pollinations (ucretsiz yedek)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from openai import APIError, AsyncOpenAI, RateLimitError

from settings import (
    DEFAULT_IMAGE_MODEL,
    get_image_model,
    get_image_provider,
    get_image_quality,
    get_image_size,
    get_openai_api_key,
    get_pollinations_api_key,
    get_pollinations_model,
    is_gpt_image_model,
    normalize_image_quality,
    normalize_image_size,
    parse_width_height,
)


class DesignError(Exception):
    """Kullaniciya gosterilebilir tasarim hatasi."""


@dataclass
class DesignResult:
    image_bytes: bytes
    revised_prompt: str | None
    provider: str = "openai"
    used_prompt: str | None = None


def _validate_user_prompt(user_prompt: str) -> str:
    text = user_prompt.strip()
    if not text:
        raise DesignError("Ne tasarlamak istedigini yazmalisin.")
    if len(text) > 900:
        raise DesignError("Aciklama en fazla 900 karakter olabilir.")
    return text


def _build_openai_prompt(user_prompt: str) -> str:
    text = _validate_user_prompt(user_prompt)
    return (
        "Create a polished visual design exactly as described. "
        "Match subject, colors, text, layout, and style from the description. "
        f"Description: {text}"
    )


def _build_pollinations_prompt(user_prompt: str) -> str:
    """Ucretsiz model icin net, kisa Ingilizce yonlendirme + kullanici metni."""
    text = _validate_user_prompt(user_prompt)
    return (
        f"Draw exactly what the user asked, no unrelated people or portraits. "
        f"User request: {text}"
    )


def _is_image_bytes(data: bytes) -> bool:
    if len(data) < 8_000:
        return False
    if data.startswith((b"\xff\xd8", b"\x89PNG", b"RIFF", b"GIF8")):
        return True
    return False


def _http_request(url: str, timeout: int = 180, method: str = "GET", body: bytes | None = None) -> bytes:
    headers = {
        "User-Agent": "DiscordTasarlaBot/1.0",
        "Accept": "image/*,application/json,*/*",
    }
    if body:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise DesignError(f"Gorsel servisi hata {e.code}") from e
    except urllib.error.URLError as e:
        raise DesignError(f"Gorsel indirilemedi: {e}") from e


def _download_image(url: str, timeout: int = 180) -> bytes:
    data = _http_request(url, timeout=timeout)
    if not data:
        raise DesignError("Bos gorsel yaniti alindi.")
    if data.lstrip().startswith(b"<"):
        raise DesignError("Gorsel servisi gecersiz yanit dondurdu (HTML).")
    if not _is_image_bytes(data):
        raise DesignError("Gecerli gorsel dosyasi alinamadi, tekrar dene.")
    return data


def _prompt_seed(text: str) -> int:
    return int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)


async def _fetch_pollinations_get(prompt: str, seed: int) -> bytes:
    w, h = parse_width_height(get_image_size())
    model = get_pollinations_model()
    params = {
        "width": w,
        "height": h,
        "model": model,
        "seed": seed,
        "enhance": "true",
        "private": "true",
        "nologo": "true",
        "safe": "false",
    }
    api_key = get_pollinations_api_key()
    if api_key:
        params["key"] = api_key
    query = urllib.parse.urlencode(params)
    encoded_prompt = urllib.parse.quote(prompt, safe="")
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?{query}"
    return await asyncio.to_thread(_download_image, url)


async def _fetch_pollinations_post(prompt: str) -> bytes:
    """gen.pollinations.ai — daha tutarli sonuc."""
    api_key = get_pollinations_api_key()
    w, h = parse_width_height(get_image_size())
    payload = {
        "model": get_pollinations_model(),
        "prompt": prompt,
        "size": f"{w}x{h}",
        "n": 1,
        "response_format": "b64_json",
    }
    body = json.dumps(payload).encode("utf-8")
    url = "https://gen.pollinations.ai/v1/images/generations"
    if api_key:
        url = f"{url}?key={urllib.parse.quote(api_key)}"
    raw = await asyncio.to_thread(_http_request, url, 180, "POST", body)

    try:
        parsed = json.loads(raw.decode("utf-8"))
        item = parsed["data"][0]
        if item.get("b64_json"):
            img = base64.b64decode(item["b64_json"])
            if _is_image_bytes(img):
                return img
        if item.get("url"):
            return await asyncio.to_thread(_download_image, item["url"])
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        pass

    if _is_image_bytes(raw):
        return raw
    raise DesignError("Pollinations JSON yaniti okunamadi.")


async def _generate_pollinations(user_prompt: str) -> DesignResult:
    prompt = _build_pollinations_prompt(user_prompt)
    seed = _prompt_seed(user_prompt)
    last_err: Exception | None = None

    for attempt, seed_delta in enumerate((0, 1, 2)):
        try:
            if attempt == 0 and get_pollinations_api_key():
                image_bytes = await _fetch_pollinations_post(prompt)
            else:
                image_bytes = await _fetch_pollinations_get(prompt, seed + seed_delta)
            return DesignResult(
                image_bytes=image_bytes,
                revised_prompt=prompt,
                provider="pollinations",
                used_prompt=prompt,
            )
        except DesignError as e:
            last_err = e
            continue

    raise DesignError(
        f"Ucretsiz gorsel servisi basarisiz: {last_err}. "
        "OpenAI faturasini acinca kalite duzelir (IMAGE_PROVIDER=openai)."
    ) from last_err


def _build_kwargs(model: str, prompt: str) -> dict:
    size = normalize_image_size(model, get_image_size())
    quality = normalize_image_quality(model, get_image_quality())

    kwargs: dict = {
        "model": model,
        "prompt": prompt,
        "n": 1,
    }
    if size:
        kwargs["size"] = size
    if quality and (is_gpt_image_model(model) or model == "dall-e-3"):
        kwargs["quality"] = quality
    return kwargs


def _models_to_try(primary: str) -> list[str]:
    order: list[str] = [primary]
    for fallback in (DEFAULT_IMAGE_MODEL, "gpt-image-1-mini"):
        if fallback not in order:
            order.append(fallback)
    return order


def _is_invalid_model_error(err: APIError) -> bool:
    msg = (err.message or str(err)).lower()
    return "does not exist" in msg or "invalid_value" in msg


def _is_billing_error(err: APIError) -> bool:
    msg = (err.message or str(err)).lower()
    return "billing" in msg or "insufficient_quota" in msg


def _billing_help() -> str:
    return (
        "OpenAI odeme limiti dolmus — gorseller yanlis veya dusuk kalite olabilir.\n"
        "Kaliteli sonuc icin: https://platform.openai.com/settings/organization/billing\n"
        "Gecici cozum: `.env` → `IMAGE_PROVIDER=pollinations` (ucretsiz, daha az guvenilir)"
    )


async def _generate_openai(prompt: str, user_prompt: str) -> DesignResult:
    api_key = get_openai_api_key()
    if not api_key:
        raise DesignError(
            "OPENAI_API_KEY yok. Anahtar ekle veya `IMAGE_PROVIDER=pollinations` kullan."
        )

    client = AsyncOpenAI(api_key=api_key)
    primary = get_image_model()
    last_error: Exception | None = None
    response = None

    for model in _models_to_try(primary):
        kwargs = _build_kwargs(model, prompt)
        try:
            response = await client.images.generate(**kwargs)
            break
        except RateLimitError:
            raise DesignError("OpenAI kotasi dolmus veya cok hizli istek. Biraz sonra tekrar dene.")
        except APIError as e:
            last_error = e
            if _is_billing_error(e):
                raise
            if _is_invalid_model_error(e) and model != _models_to_try(primary)[-1]:
                continue
            raise DesignError(f"OpenAI hatasi: {e.message or e}") from e
        except Exception as e:
            raise DesignError(f"AI baglantisi basarisiz: {e}") from e
    else:
        raise DesignError(f"OpenAI hatasi: {last_error}") from last_error

    if not response or not response.data:
        raise DesignError("AI gorsel uretemedi.")

    item = response.data[0]
    revised = getattr(item, "revised_prompt", None)

    if item.b64_json:
        image_bytes = base64.b64decode(item.b64_json)
    elif item.url:
        image_bytes = await asyncio.to_thread(_download_image, item.url)
    else:
        raise DesignError("AI gecerli gorsel verisi dondurmedi.")

    return DesignResult(
        image_bytes=image_bytes,
        revised_prompt=revised,
        provider="openai",
        used_prompt=prompt,
    )


async def generate_design(user_prompt: str) -> DesignResult:
    openai_prompt = _build_openai_prompt(user_prompt)
    provider = get_image_provider()

    if provider == "pollinations":
        return await _generate_pollinations(user_prompt)

    if provider == "openai":
        try:
            return await _generate_openai(openai_prompt, user_prompt)
        except APIError as e:
            if _is_billing_error(e):
                raise DesignError(_billing_help()) from e
            raise DesignError(f"OpenAI hatasi: {e.message or e}") from e

    if get_openai_api_key():
        try:
            return await _generate_openai(openai_prompt, user_prompt)
        except APIError as e:
            if _is_billing_error(e) or _is_invalid_model_error(e):
                print("OpenAI kullanilamadi, Pollinations yedegine geciliyor...", flush=True)
                result = await _generate_pollinations(user_prompt)
                return result
            raise DesignError(f"OpenAI hatasi: {e.message or e}") from e

    return await _generate_pollinations(user_prompt)


def image_to_discord_file(image_bytes: bytes, filename: str = "tasarim.png"):
    import discord

    buf = io.BytesIO(image_bytes)
    buf.seek(0)
    return discord.File(buf, filename=filename)
