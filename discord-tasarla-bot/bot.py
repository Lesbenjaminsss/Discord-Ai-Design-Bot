"""
Discord AI tasarim botu — sadece /tasarla ve /yardim.
Ayri Discord uygulamasi (yeni bot token) gerekir.
"""
import sys
import time

import discord
from discord import app_commands

from image_design import DesignError, generate_design, image_to_discord_file
from settings import (
    OWNER_ID,
    check_token,
    get_guild_id,
    get_tasarla_cooldown_sec,
    get_token,
)

_cooldown: dict[int, float] = {}


def is_owner(uid: int) -> bool:
    return uid == OWNER_ID


class TasarlaBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self._synced = False

    async def _sync_commands(self) -> None:
        gid = get_guild_id()
        if gid.isdigit():
            guild_id = int(gid)
            guild_obj = self.get_guild(guild_id)
            if guild_obj is None:
                try:
                    guild_obj = await self.fetch_guild(guild_id)
                except (discord.NotFound, discord.Forbidden):
                    guild_obj = None
            if guild_obj is None:
                print()
                print("=" * 50, flush=True)
                print("HATA: Bot bu sunucuda YOK (403 Missing Access)", flush=True)
                print(f"  DISCORD_GUILD_ID = {gid}", flush=True)
                print("  Cozum: Botu sunucuya ekle (asagidaki README invite linki)", flush=True)
                print("  scopes: bot + applications.commands", flush=True)
                print("=" * 50, flush=True)
                return
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            try:
                synced = await self.tree.sync(guild=guild)
                where = f"sunucu {gid}"
            except discord.Forbidden:
                print(
                    f"UYARI: Sunucu {gid} komut senkronu reddedildi — bot kanal/rol yetkisi kontrol et.",
                    flush=True,
                )
                synced = await self.tree.sync()
                where = "global (yedek)"
        else:
            synced = await self.tree.sync()
            where = "global"
        names = [c.name for c in synced]
        print(f"Komutlar [{where}]: {', '.join(f'/{n}' for n in names)}", flush=True)

    async def on_ready(self) -> None:
        if not self._synced:
            self._synced = True
            await self._sync_commands()

        print("=" * 50, flush=True)
        print("TASARLA BOT AKTIF", flush=True)
        print(f"  {self.user} ({self.user.id})", flush=True)
        print("  /tasarla — AI gorsel uret", flush=True)
        print("=" * 50, flush=True)
        await self.change_presence(activity=discord.Game(name="/tasarla"))


client = TasarlaBot()


@client.tree.command(
    name="tasarla",
    description="AI ile istedigin gorseli tasarlat (logo, afis, karakter vb.)",
)
@app_commands.describe(
    istek="Ne tasarlanacak? Ornek: mavi neon sunucu logosu, gece sehri arka plan",
)
async def cmd_tasarla(i: discord.Interaction, istek: str):
    uid = i.user.id
    cooldown = get_tasarla_cooldown_sec()
    if cooldown > 0 and not is_owner(uid):
        last = _cooldown.get(uid, 0.0)
        wait = cooldown - (time.time() - last)
        if wait > 0:
            return await i.response.send_message(
                f"Biraz bekle — **{int(wait) + 1}** saniye sonra tekrar dene.",
                ephemeral=True,
            )

    await i.response.defer(thinking=True)
    try:
        result = await generate_design(istek)
    except DesignError as e:
        return await i.followup.send(str(e), ephemeral=True)
    except Exception:
        return await i.followup.send(
            "Tasarim sirasinda beklenmeyen hata. Terminal loguna bak.",
            ephemeral=True,
        )

    _cooldown[uid] = time.time()
    file = image_to_discord_file(result.image_bytes)
    title = "Tasarim hazir"
    if result.provider == "pollinations":
        title = "Tasarim hazir (ucretsiz mod)"
    emb = discord.Embed(
        title=title,
        description=istek[:500],
        color=0x9B59B6,
    )
    emb.set_image(url="attachment://tasarim.png")
    if result.provider == "pollinations":
        emb.add_field(
            name="Uyari",
            value=(
                "OpenAI limitin dolu — ucretsiz yedek kullanildi. "
                "Sonuc bazen istekle uyusmayabilir. "
                "Kalite icin OpenAI faturasini ac: `IMAGE_PROVIDER=openai`"
            ),
            inline=False,
        )
    footer = f"Isteyen: {i.user.display_name}"
    emb.set_footer(text=footer)
    if result.revised_prompt and result.revised_prompt != istek:
        emb.add_field(
            name="AI yorumu",
            value=result.revised_prompt[:900],
            inline=False,
        )
    try:
        await i.followup.send(embed=emb, file=file)
    except discord.Forbidden:
        await i.followup.send(
            "Bu kanala mesaj/gorsel gonderme yetkim yok. "
            "Kanal izinlerinde **Mesaj Gonder**, **Dosya Ekle**, **Baglanti Gom** ac.",
            ephemeral=True,
        )


@client.tree.command(name="yardim", description="Komut listesi")
async def cmd_yardim(i: discord.Interaction):
    emb = discord.Embed(title="Tasarla Bot", color=0x9B59B6)
    emb.add_field(
        name="Komut",
        value="`/tasarla istek:...` — aciklamaya gore AI gorsel uretir",
        inline=False,
    )
    emb.set_footer(text="OpenAI API anahtari ve kredi gerekir")
    await i.response.send_message(embed=emb)


@client.tree.error
async def tree_error(i: discord.Interaction, err: app_commands.AppCommandError):
    msg = f"Hata: {err}"
    if i.response.is_done():
        await i.followup.send(msg, ephemeral=True)
    else:
        await i.response.send_message(msg, ephemeral=True)


def main() -> None:
    token = get_token()
    ok, msg = check_token(token)
    print(msg)
    if not ok:
        print(f"\n.env yolu: {__import__('settings').ENV_PATH}")
        sys.exit(1)

    gid = get_guild_id()
    if not gid.isdigit():
        print()
        print("ONEMLI: .env dosyasina DISCORD_GUILD_ID ekle (komutlar hemen gorunsun)")

    client.run(token)


if __name__ == "__main__":
    main()
