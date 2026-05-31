# Discord Tasarla Botu

Sadece AI gorsel uretimi: `/tasarla`

Casino botundan (`discord-bot`) tamamen ayri. **Yeni bir Discord uygulamasi** olusturup onun tokenini kullan.

## Kurulum

1. [Discord Developer Portal](https://discord.com/developers/applications) -> **New Application** -> Bot -> token al
2. OAuth2 URL Generator:
   - Scopes: `bot` + `applications.commands`
   - Bot permissions: **Mesaj Gonder**, **Dosya Ekle**, **Baglanti Gom**, **Mesaj Gecmisini Oku**
   - Linki acip **ayni sunucuya** ekle (`.env` icindeki `DISCORD_GUILD_ID` ile ayni olmali)
3. Developer Portal -> **OAuth2** -> Client ID ile invite:
   `https://discord.com/api/oauth2/authorize?client_id=BURAYA_CLIENT_ID&permissions=116736&scope=bot%20applications.commands`
4. [OpenAI API key](https://platform.openai.com/api-keys) al (kredi gerekir)
5. Bu klasorde:

```
pip install -r requirements.txt
copy .env.example .env
```

`.env` icine yaz:

```
DISCORD_TOKEN=...
DISCORD_GUILD_ID=...
OPENAI_API_KEY=...
```

6. `python token_kontrol.py` sonra `python bot.py` (veya `baslat.bat`)

**Gorsel model:** `IMAGE_MODEL=gpt-image-1` (DALL-E 3 kaldirildi).

**Odeme limiti dolunca:** `IMAGE_PROVIDER=auto` (varsayilan) ucretsiz **Pollinations** yedegine gecer.
Sadece ucretsiz: `IMAGE_PROVIDER=pollinations`
Sadece OpenAI: `IMAGE_PROVIDER=openai` (+ faturalama limiti acik olmali)

OpenAI limit cozumu: https://platform.openai.com/settings/organization/billing

## 403 Missing Access (50001)

Bot **sunucuda degil** veya **kanalda yetki yok**.

1. Tasarla botunu casino botundan **ayri** uygulama olarak sunucuya tekrar davet et
2. `.env` `DISCORD_GUILD_ID` = davet ettigin sunucunun ID (sag tik sunucu -> Sunucu Kimligini Kopyala)
3. `/tasarla` kullandigin kanalda bota izin ver (rol veya kanal ayari)

## Komutlar

| Komut      | Aciklama              |
| ---------- | --------------------- |
| `/tasarla` | AI ile gorsel uret    |
| `/yardim`  | Kisa bilgi            |

## Klasor

`c:\Users\lesbe\Projects\mta-phone\discord-tasarla-bot`
