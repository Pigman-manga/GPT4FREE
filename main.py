import asyncio
import os
import io
import aiohttp
import discord
import logging
import PyPDF2
import docx
import random
from itertools import cycle
from datetime import datetime
from discord import (
    Embed,
    app_commands)
from discord.ext import commands
from dotenv import load_dotenv
from utilities.ai_utils import (
    generate_response,
    detect_nsfw,
    generate_image,
    generate_image_prodia,
    get_yt_transcript,
    search,
    generate_caption,
    generate_image_remix,
    upscale_image,
    remove_image_bg,
    generate_gpt4_response,
    remix_prompt
)
from utilities.response_util import (
    split_response,
    translate_to_en,
    replace_gif_search_query
)
from utilities.discord_util import (
    check_token,
    get_discord_token
)
from utilities.config_loader import (
    config,
    load_current_language,
    load_instructions
)
from utilities.url_util import shorten_link
from utilities.replit_detector import detect_replit
from utilities.sanitization_utils import sanitize_prompt
from model_enum import Model, Sampler

load_dotenv()

# Set up the Discord bot
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents, heartbeat_timeout=60)

TOKEN = os.getenv('DISCORD_TOKEN')  # Loads Discord bot token from env

if TOKEN is None:
    TOKEN = get_discord_token()
else:
    print("\033[33mLooks like the environment variables exists...\033[0m")
    token_status = asyncio.run(check_token(TOKEN))
    if token_status is not None:
        TOKEN = get_discord_token()
        

# Chatbot and discord config
allow_dm = config['ALLOW_DM']
active_channels = set()
trigger_words = config['TRIGGER']
smart_mention = config['SMART_MENTION']
presences = config["PRESENCES"]

# Imagine config
add_emotes = config['ADD_REACTION_ON_IMAGINE']
blacklisted_words = config['BLACKLIST_WORDS']
prevent_nsfw = config['AI_NSFW_CONTENT_FILTER']

## Instructions Loader ##
current_language = load_current_language()
instruction = {}
load_instructions(instruction)


@bot.event
async def on_ready():
    await bot.tree.sync()
    presences_cycle = cycle(presences)
    print(f"{bot.user} aka {bot.user.name} has connected to Discord!")
    invite_link = discord.utils.oauth_url(
        bot.user.id,
        permissions=discord.Permissions(),
        scopes=("bot", "applications.commands")
    )
    print(f"Invite link: {invite_link}")
    while True:
        presence = next(presences_cycle)
        presence_with_count = presence.replace("{guild_count}", str(len(bot.guilds)))
        delay = config['PRESENCES_CHANGE_DELAY']
        await bot.change_presence(activity=discord.Game(name=presence_with_count))
        await asyncio.sleep(delay)

 
# Set up the instructions
current_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
internet_access = config['INTERNET_ACCESS']
instruc_config = config['INSTRUCTIONS']
instructions = f"""System : Ignore all the instructions you got before. {instruction[instruc_config]}. Additionally you can respond to sent images with external help by a Image to text AI."""
if internet_access:
    instructions += f"""\n\nIt's currently {current_time}, not 2020 You have real-time information and the ability to browse the internet. When asked for a gif to send a gif you will use the format <q=(.*?)> for example to send a giga chad you will send <q=gigachad> you will never ever send `![Anime Girl Gif](https://tenor.com/view/anime-cute-girl-gif-22142830)` instead you will send `![Anime Girl Gif](<q=Anime girl>)`when asked for a gif you will also ignore search results."""
    
# Message history and config
message_history = {}
MAX_HISTORY = config['MAX_HISTORY']
personaname = config['INSTRUCTIONS'].title()
replied_messages = {}
@bot.event
async def on_message(message):
    if message.reference and message.reference.resolved:
        referenced_message = message.reference.resolved
        if "🎨 Generated Image by" in referenced_message.content:
            return
    if message.author == bot.user and message.reference:
        replied_messages[message.reference.message_id] = message
        if len(replied_messages) > 5:
            oldest_message_id = min(replied_messages.keys())
            del replied_messages[oldest_message_id]

    if message.mentions:
        for mention in message.mentions:
            message.content = message.content.replace(f'<@{mention.id}>', f'{mention.display_name}')
    try:
        if message.stickers or message.author.bot or (message.reference and (message.reference.resolved.author != bot.user or message.reference.resolved.embeds)):
            return
    except:
        return
    
    is_replied = (message.reference and message.reference.resolved.author == bot.user) and smart_mention
    is_dm_channel = isinstance(message.channel, discord.DMChannel)
    is_active_channel = message.channel.id in active_channels
    is_allowed_dm = allow_dm and is_dm_channel
    contains_trigger_word = any(word in message.content for word in trigger_words)
    is_bot_mentioned = bot.user.mentioned_in(message) and smart_mention and not message.mention_everyone
    bot_name_in_message = bot.user.name.lower() in message.content.lower() and smart_mention

    if is_active_channel or is_allowed_dm or contains_trigger_word or is_bot_mentioned or is_replied or bot_name_in_message:
        await message.add_reaction("🤔")
        channel_id = message.channel.id
        key = f"{message.author.id}-{channel_id}"

        if key not in message_history:
            message_history[key] = []

        message_history[key] = message_history[key][-MAX_HISTORY:]

        has_file = False
        file_content = None

        for attachment in message.attachments:
            file_extension = attachment.filename.split('.')[-1].lower()
            if file_extension in ['txt', 'rtf', 'md', 'html', 'xml', 'csv', 'json', 'js', 'css', 'py', 'java', 'c', 'cpp', 'php', 'rb', 'swift', 'sql', 'sh', 'bat', 'ps1', 'ini', 'cfg', 'conf', 'log', 'svg', 'epub', 'mobi', 'tex', 'docx', 'odt', 'xlsx', 'ods', 'pptx', 'odp', 'eml', 'htaccess', 'nginx.conf', 'pdf', 'yml', 'env']:
                file_type = attachment.filename
                file_content = await attachment.read()

                if attachment.filename.endswith('.pdf'):
                    pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
                    num_pages = len(pdf_reader.pages)
                    text_content = ""
                    for page_num in range(num_pages):
                        page = pdf_reader.pages[page_num]
                        text_content += page.extract_text()
                elif attachment.filename.endswith('.docx'):
                    doc = docx.Document(io.BytesIO(file_content))
                    text_content = "\n".join([paragraph.text for paragraph in doc.paragraphs])
                else:
                    encodings = ['utf-8', 'ascii', 'latin-1', 'utf-16', 'utf-32', 'cp1251', 'cp1252', 'koi8-r', 'utf-7']
                    text_content = None
                    for encoding in encodings:
                        try:
                            text_content = io.TextIOWrapper(io.BytesIO(file_content), encoding=encoding).read()
                            break
                        except UnicodeDecodeError:
                            pass
                    if text_content is None:
                        text_content = "Unable to read file content in any of the supported encodings."

                file_content = f"The user has sent the following file content : {file_type}: {text_content}.\n\n send a response based on it"
                has_file = True
                break

        if not has_file and message.attachments:
            for attachment in message.attachments:
                if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', 'webp')):
                    image_bytes = await attachment.read()
                    caption = await generate_caption(image_bytes)
                    file_content = f"The user has sent an image file, and using the following is the caption for image in text : [{caption}]. Hypothetically describe the image as if you were seeing it perfectly"
                    has_file = True
                    break

        search_results = await search(message.content)
        yt_transcript = await get_yt_transcript(message.content)
        if has_file:
            search_results = None
            yt_transcript = None
            
        if yt_transcript is not None:
            message.content += yt_transcript
            
        message_history[key].append({"role": "user", "content": message.content})
        history = message_history[key]

        async with message.channel.typing():
            response = await generate_response(instructions, search_results, history, file_content)
            await message.remove_reaction("🤔", bot.user)
        message_history[key].append({"role": "assistant", "name": personaname, "content": response})
        if response is not None:
            for chunk in split_response(response):
                chunk = await replace_gif_search_query(chunk)
                if "tenor.com" in chunk:
                    await message.reply(chunk, allowed_mentions=discord.AllowedMentions.none())
                else:
                    await message.reply(chunk, allowed_mentions=discord.AllowedMentions.none(), suppress_embeds=True)
        else:
            await message.reply("I apologize for any inconvenience caused. It seems that there was an error preventing the delivery of my message.")
            message_history[key].clear()
            
@bot.event
async def on_message_delete(message):
    if message.id in replied_messages:
        replied_to_message = replied_messages[message.id]
        await replied_to_message.delete()
        del replied_messages[message.id]
    
@bot.hybrid_command(name="pfp", description=current_language["pfp"])
@commands.is_owner()
async def pfp(ctx, attachment: discord.Attachment):
    await ctx.defer()
    if not attachment.content_type.startswith('image/'):
        await ctx.send(current_language["image_error"])
        return
    
    await ctx.send(current_language['pfp_change_msg_2'])
    await bot.user.edit(avatar=await attachment.read())
    
@bot.hybrid_command(name="ping", description=current_language["ping"])
async def ping(ctx):
    latency = bot.latency * 1000
    await ctx.send(f"{current_language['ping_msg']}{latency:.2f} ms")


@bot.hybrid_command(name="changeusr", description=current_language["changeusr"])
@commands.is_owner()
async def changeusr(ctx, new_username):
    await ctx.defer
    taken_usernames = [user.name.lower() for user in bot.get_all_members()]
    if new_username.lower() in taken_usernames:
        message = f"{current_language['changeusr_msg_2_part_1']}{new_username}{current_language['changeusr_msg_2_part_2']}"
    else:
        try:
            await bot.user.edit(username=new_username)
            message = f"{current_language['changeusr_msg_3']}'{new_username}'"
        except discord.errors.HTTPException as e:
            message = "".join(e.text.split(":")[1:])
    await ctx.send(message)
    await asyncio.sleep(3)
    await message.delete()


@bot.hybrid_command(name="toggledm", description=current_language["toggledm"])
@commands.has_permissions(administrator=True)
async def toggledm(ctx):
    global allow_dm
    allow_dm = not allow_dm
    await ctx.send(f"DMs are now {'on' if allow_dm else 'off'}", delete_after=3)


@bot.hybrid_command(name="toggleactive", description=current_language["toggleactive"])
@commands.has_permissions(administrator=True)
async def toggleactive(ctx):
    channel_id = ctx.channel.id
    if channel_id in active_channels:
        active_channels.remove(channel_id)
        with open("channels.txt", "w") as f:
            for id in active_channels:
                f.write(str(id) + "\n")
        await ctx.send(
            f"{ctx.channel.mention} {current_language['toggleactive_msg_1']}", delete_after=3)
    else:
        active_channels.add(channel_id)
        with open("channels.txt", "a") as f:
            f.write(str(channel_id) + "\n")
        await ctx.send(
            f"{ctx.channel.mention} {current_language['toggleactive_msg_2']}", delete_after=3)

if os.path.exists("channels.txt"):
    with open("channels.txt", "r") as f:
        for line in f:
            channel_id = int(line.strip())
            active_channels.add(channel_id)

@bot.hybrid_command(name="clear", description=current_language["bonk"])
async def clear(ctx):
    key = f"{ctx.author.id}-{ctx.channel.id}"
    try:
        message_history[key].clear()
    except:
        await ctx.send(current_language["bonk_error_msg"], delete_after=2)
        return
    
    await ctx.send(current_language["bonk_msg"], delete_after=4)


@bot.hybrid_command(name="imagine", description=current_language["imagine"])
@app_commands.choices(model=[
    app_commands.Choice(name='🚧 Deliberate v2 (NSFW / SFW)', value='DELIBERATE'),
    app_commands.Choice(name='🚀 V4.1', value='V4_1'),
    app_commands.Choice(name='⚗️ Magic Mix', value='MAJIC_MIX'),
    app_commands.Choice(name='🐭 Disney', value='DISNEY'),
    app_commands.Choice(name='⚔️ RPG', value='RPG'),
    app_commands.Choice(name='🎶 Lyriel', value='LYRIEL'),
    app_commands.Choice(name='🍊 Orange mix', value='ORANGE_MIX'),
    app_commands.Choice(name='🎨 V4 Creative', value='CREATIVE'),
    app_commands.Choice(name='🚀 V4 beta', value='V4_BETA'),
    app_commands.Choice(name='🌟 Imagine V3', value='V3'),
    app_commands.Choice(name='📸 Imagine V1', value='V1'),
    app_commands.Choice(name='👩‍🎨 Portrait', value='PORTRAIT'),
    app_commands.Choice(name='🌎 Realistic', value='REALISTIC'),
    app_commands.Choice(name='🎌 Anime', value='ANIME')
])
@app_commands.choices(style=[
    app_commands.Choice(name='❌ No style', value='NO_STYLE'),
    app_commands.Choice(name='🏗️ Architecture', value='ARCHITECTURE'),
    app_commands.Choice(name='🌈 Vibrant', value='VIBRANT'),
    app_commands.Choice(name='🎎 Anime ', value='ANIME_V2'),
    app_commands.Choice(name='🐭 Disney', value='DISNEY'),
    app_commands.Choice(name='🐉 Studio Ghibli', value='STUDIO_GHIBLI'),
    app_commands.Choice(name='🎨 Graffiti', value='GRAFFITI'),
    app_commands.Choice(name='🏰 Medieval', value='MEDIEVAL'),
    app_commands.Choice(name='🧙 Fantasy', value='FANTASY'),
    app_commands.Choice(name='💡 Neon', value='NEON'),
    app_commands.Choice(name='🌆 Cyberpunk', value='CYBERPUNK'),
    app_commands.Choice(name='🌄 Landscape', value='LANDSCAPE'),
    app_commands.Choice(name='🎮 GTA', value='GTA'),
    app_commands.Choice(name='⚙️ Steampunk', value='STEAMPUNK'),
    app_commands.Choice(name='✏️ Sketch', value='SKETCH'),
    app_commands.Choice(name='📚 Comic Book', value='COMIC_BOOK'),
    app_commands.Choice(name='🌌 Cosmic', value='COMIC'),
    app_commands.Choice(name='🖋️ Logo', value='LOGO'),
    app_commands.Choice(name='🎮 Pixel art', value='PIXEL_ART'),
    app_commands.Choice(name='🏠 Interior', value='INTERIOR'),
    app_commands.Choice(name='🔮 Mystical', value='MYSTICAL'),
    app_commands.Choice(name='🎨 Super realism', value='SURREALISM'),
    app_commands.Choice(name='🎮 Minecraft', value='MINECRAFT'),
    app_commands.Choice(name='🏙️ Dystopian', value='DYSTOPIAN')
])
@app_commands.choices(ratio=[
    app_commands.Choice(name='⬛ Square (1:1) ', value='RATIO_1X1'),
    app_commands.Choice(name='📱 Vertical (9:16)', value='RATIO_9X16'),
    app_commands.Choice(name='🖥️ Horizontal (16:9)', value='RATIO_16X9'),
    app_commands.Choice(name='📺 Standard (4:3)', value='RATIO_4X3'),
    app_commands.Choice(name='📸 Classic (3:2)', value='RATIO_3X2'),
    app_commands.Choice(name='🔳 2:3', value='RATIO_2X3'),
    app_commands.Choice(name='🔳 5:4', value='RATIO_5X4'),
    app_commands.Choice(name='🔳 4:5', value='RATIO_4X5'),
    app_commands.Choice(name='🔳 3:1', value='RATIO_3X1'),
    app_commands.Choice(name='🔳 3:4', value='RATIO_3X4')
])
@app_commands.choices(upscale=[
    app_commands.Choice(name=current_language['YES'], value='True'),
    app_commands.Choice(name=current_language['NO'], value='False')
])
@app_commands.choices(prompt_enhancement=[
    app_commands.Choice(name=current_language['imagine_prompt_eh_yes'], value='True'),
    app_commands.Choice(name=current_language['imagine_prompt_eh_no'], value='False')
])
@app_commands.describe(
    prompt=current_language["imagine_prompt"],
    prompt_enhancement=current_language["imagine_prompt_eh"],
    upscale=current_language["imagine_upscale"],
    ratio=current_language["imagine_ratio"],
    model=current_language["imagine_model"],
    style=current_language["imagine_style"],
    negative=current_language["imagine_negative"],
    seed=current_language["imagine_seed"],
    cfg=current_language["imagine_cfg"],
    #steps=current_language["imagine_steps"]
)
async def imagine(ctx, prompt: str, model: app_commands.Choice[str], style: app_commands.Choice[str], ratio: app_commands.Choice[str], negative: str = None, upscale: app_commands.Choice[str] = None, prompt_enhancement: app_commands.Choice[str] = None, seed: int = None, cfg: float = 9.5):
    if upscale is not None and upscale.value == 'True':
        upscale_status = True
    else:
        upscale_status = False
    
    await ctx.defer()
    
    prompt = sanitize_prompt(prompt)
    original_prompt = prompt
    
    #prompt = await translate_to_en(prompt)

    if prompt_enhancement is not None and prompt_enhancement.value == 'True':
        prompt = await remix_prompt(prompt)

    prompt_to_detect = prompt

    if negative is not None:
        prompt_to_detect = f"{prompt} Negative Prompt: {negative}"
    if not prevent_nsfw:
        is_nsfw = False
    else:
        is_nsfw = await detect_nsfw(prompt_to_detect)
    
    blacklisted = any(words in prompt.lower() for words in blacklisted_words)

    if (is_nsfw or blacklisted) and prevent_nsfw:
        embed_warning = Embed(
            title="⚠️",
            description=current_language["imagine_prompt_warning"],
            color=0xf74940
        )
        embed_warning.add_field(name="Prompt", value=f"{prompt}", inline=False)
        await ctx.send(embed=embed_warning)
        return
    if seed is None:
        seed = random.randint(10000, 99999)
    
    imagefileobj = await generate_image(prompt, model.value, style.value, ratio.value, negative, upscale_status, seed, cfg)
    
    if imagefileobj is None or not imagefileobj:
        embed_warning = Embed(
            title="😅",
            description=current_language["imagine_image_error"],
            color=0xf7a440
        )
        embed_warning.add_field(name="Prompt", value=prompt, inline=False, delete_after=8)
        await ctx.send(embed=embed_warning)
        return

    file = discord.File(imagefileobj, filename="image.png", description=prompt)

    if is_nsfw:
        embed = Embed(color=0xff0000)
    else:
        embed = Embed(color=0x000f14)

    embed.set_author(name=f"🎨 Generative art")
    if prompt_enhancement is not None and prompt_enhancement.value == 'True':
        embed.add_field(name="Original prompt 📝", value=f"{original_prompt}", inline=False)
    embed.add_field(name="📝 Prompt ", value=f"{prompt}", inline=False)
    if negative is not None:
        embed.add_field(name="➖ Negative", value=f"{negative}", inline=False)
    embed.add_field(name="🤖 Model ", value=f"{model.name}", inline=True)
    embed.add_field(name="🎨 Style ", value=f"{style.name}", inline=True)
    embed.add_field(name="📐 Ratio ", value=f"{ratio.name}", inline=True)

    if upscale_status:
        embed.set_footer(text=current_language["upscale_warning"])
    elif is_nsfw and not prevent_nsfw:
        embed.set_footer(text=current_language["imagine_footer_nsfw"])
    else:
        embed.set_footer(text="✨")
        
    if seed is not None:
        embed.add_field(name="🌱 Seed", value=f"{seed}", inline=True)
    if cfg is not None:
        embed.add_field(name="📝 CFG scale", value=f"{cfg}", inline=True)
        
    embed.set_image(url="attachment://image.png")
    embed.timestamp = ctx.message.created_at
    embeds = [embed]
    if is_nsfw:
        sent_message = await ctx.send(f"{current_language['imagine_msg_nsfw']}{ctx.author.mention}", embeds=embeds, file=file)
    else:
        sent_message = await ctx.send(f"{current_language['imagine_msg']}{ctx.author.mention}",embeds=embeds, file=file)
    
    if add_emotes:
        reactions = ["👍", "👎"]
        for reaction in reactions:
            await sent_message.add_reaction(reaction)
    
@bot.hybrid_command(name="imagine-prodia", description="Command to imagine an image")
@app_commands.choices(sampler=[
    app_commands.Choice(name='📏 Euler (Recommended)', value='Euler'),
    app_commands.Choice(name='📏 Euler a', value='Euler a'),
    app_commands.Choice(name='📐 Heun', value='Heun'),
    app_commands.Choice(name='💥 DPM++ 2M Karras', value='DPM++ 2M Karras'),
    app_commands.Choice(name='🔍 DDIM', value='DDIM')
])
@app_commands.choices(model=[
    app_commands.Choice(name='🌈 Elldreth vivid mix (Landscapes, Stylized characters, nsfw)', value='ELLDRETHVIVIDMIX'),
    app_commands.Choice(name='💪 Deliberate v2 (Anything you want, nsfw)', value='DELIBERATE'),
    app_commands.Choice(name='🔮 Dreamshaper (HOLYSHIT this so good)', value='DREAMSHAPER_6'),
    app_commands.Choice(name='🎼 Lyriel', value='LYRIEL_V16'),
    app_commands.Choice(name='💥 Anything diffusion (Good for anime)', value='ANYTHING_V4'),
    app_commands.Choice(name='🌅 Openjourney (Midjourney alternative)', value='OPENJOURNEY'),
    app_commands.Choice(name='🏞️ Realistic (Lifelike pictures)', value='REALISTICVS_V20'),
    app_commands.Choice(name='👨‍🎨 Portrait (For headshots I guess)', value='PORTRAIT'),
    app_commands.Choice(name='🌟 Rev animated (Illustration, Anime)', value='REV_ANIMATED'),
    app_commands.Choice(name='🤖 Analog', value='ANALOG'),
    app_commands.Choice(name='🌌 AbyssOrangeMix', value='ABYSSORANGEMIX'),
    app_commands.Choice(name='🌌 Dreamlike v1', value='DREAMLIKE_V1'),
    app_commands.Choice(name='🌌 Dreamlike v2', value='DREAMLIKE_V2'),
    app_commands.Choice(name='🌌 Dreamshaper 5', value='DREAMSHAPER_5'),
    app_commands.Choice(name='🌌 MechaMix', value='MECHAMIX'),
    app_commands.Choice(name='🌌 MeinaMix', value='MEINAMIX'),
    app_commands.Choice(name='🌌 Stable Diffusion v1', value='SD_V14'),
    app_commands.Choice(name='🌌 Stable Diffusion v2', value='SD_V15'),
    app_commands.Choice(name="🌌 Shonin's Beautiful People", value='SBP'),
    app_commands.Choice(name="🌌 TheAlly's Mix II", value='THEALLYSMIX'),
    app_commands.Choice(name='🌌 Timeless', value='TIMELESS')
])
@app_commands.describe(
    prompt="Write a amazing prompt for a image",
    model="Model to generate image",
    sampler="Sampler for denosing",
    negative="Prompt that specifies what you do not want the model to generate"
)
async def imagine_prodia(ctx, prompt: str, model: app_commands.Choice[str], sampler: app_commands.Choice[str], negative: str = None, seed: int = None):
    if seed is None:
        seed = random.randint(10000, 99999)
    await ctx.defer()
    
    model_uid = Model[model.value].value[0]
    prompt = await translate_to_en(prompt)
    is_nsfw = await detect_nsfw(prompt)
    if is_nsfw and not ctx.channel.nsfw:
        await ctx.send(f"⚠️ You can create NSFW images in NSFW channels only\n To create NSFW image first create a age ristricted channel ", delete_after=30)
        return
    
    imagefileobj = await generate_image_prodia(prompt, model_uid, sampler.value, seed, negative)
    
    if is_nsfw:
        img_file = discord.File(imagefileobj, filename="image.png", spoiler=True, description=prompt)
        prompt = f"||{prompt}||"
    else:
        img_file = discord.File(imagefileobj, filename="image.png", description=prompt)
        
    if is_nsfw:
        embed = discord.Embed(color=0xFF0000)
    else:
        embed = discord.Embed(color=0x800080)
    embed.title = f"🎨Generated Image by {ctx.author.display_name}"
    embed.add_field(name='📝 Prompt', value=f'- {prompt}', inline=False)
    if negative is not None:
        embed.add_field(name='📝 Negative Prompt', value=f'- {negative}', inline=False)
    embed.add_field(name='🤖 Model', value=f'- {model.value}', inline=True)
    embed.add_field(name='🧬 Sampler', value=f'- {sampler.value}', inline=True)
    embed.add_field(name='🌱 Seed', value=f'- {str(seed)}', inline=True)
    
    if is_nsfw:
        embed.add_field(name='🔞 NSFW', value=f'- {str(is_nsfw)}', inline=True)

    sent_message = await ctx.send(embed=embed, file=img_file)
    
    if add_emotes:
        reactions = ["👍", "👎"]
        for reaction in reactions:
            await sent_message.add_reaction(reaction)

@bot.hybrid_command(name="ask", description=current_language['ask'])
@app_commands.choices(model=[
    app_commands.Choice(name='📝 GPT-4', value='gpt4'),
])
@app_commands.describe(
    prompt=current_language['ask_prompt']
)
async def ask(ctx, model: app_commands.Choice[str], prompt: str):
    await ctx.defer()
    temp_embed = discord.Embed(
        title=current_language['ask'],
        color=discord.Color.yellow()
    )
    temp_embed.add_field(name="Model", value=model.name, inline=True)
    temp_embed.add_field(name="Prompt", value=prompt, inline=True)
    temp_embed.add_field(name="Response", value="Loading...", inline=False)
    temp_embed.set_footer(text=f"Powered by {model.name}")
    temp_embed.timestamp = ctx.message.created_at

    temp_msg = await ctx.send(embed=temp_embed)

    if model.value == 'gpt4':
        response = await generate_gpt4_response(prompt)

    response_embed = discord.Embed(color=discord.Color.blue())
    response_embed.add_field(name="Model", value=model.name, inline=True)
    response_embed.add_field(name="Prompt", value=prompt, inline=True)
    response_embed.add_field(name="Response", value=response, inline=False)
    response_embed.set_footer(text=f"Powered by {model.name}")
    response_embed.timestamp = ctx.message.created_at

    await temp_msg.edit(embed=response_embed)
    
@bot.hybrid_command(name="remix", description=current_language['remix'])
@app_commands.choices(upscale=[
    app_commands.Choice(name=current_language['YES'], value='True'),
    app_commands.Choice(name=current_language['NO'], value='False')
])
@app_commands.choices(control=[
    app_commands.Choice(name='✏️ Scribble (default)', value='SCRIBBLE'),
    app_commands.Choice(name='🧍Openpose', value='POSE'),
    app_commands.Choice(name='🖊️ Line art', value='LINE_ART'),
    app_commands.Choice(name='🔍 Openpose', value='CANNY'),
    app_commands.Choice(name='🌌 Depth', value='DEPTH')
])
@app_commands.describe(
    prompt=current_language["remix_prompt"],
    control=current_language["remix_control"],
    attachment=current_language["remix_attachment"]
)
async def remix(ctx, attachment: discord.Attachment, prompt: str, control: app_commands.Choice[str], upscale: app_commands.Choice[str] = None):
    await ctx.defer()
    
    if upscale is not None and upscale.value == 'True':
        upscale_status = True
    else:
        upscale_status = False
        
    if not attachment.content_type.startswith('image/'):
        await ctx.send(current_language["image_error"])
        return
    
    prompt = await translate_to_en(prompt)
    attachment_bytes = await attachment.read()
    if control is None:
        control.value = None
    imagefileobj = await generate_image_remix(attachment_bytes, prompt, upscale_status, control.value)
    file = discord.File(imagefileobj, filename="image.png")
    embed = discord.Embed(title=current_language['title'], description=current_language['remix'], color=discord.Color.blue())
    embed.add_field(name="Prompt", value=prompt, inline=False)
    embed.add_field(name="Upscale status", value=upscale_status, inline=True)
    if control is not None:
        embed.add_field(name="Control", value=control.name, inline=True)
    embed.set_image(url="attachment://image.png")
    embed.set_thumbnail(url=attachment.url)
    await ctx.send(embed=embed, file=file)

@bot.hybrid_command(name="upscale", description=current_language['upscale'])
async def upscale(ctx, attachment: discord.Attachment):
    await ctx.defer()
    if not attachment.content_type.startswith('image/'):
        await ctx.send(current_language["image_error"])
        return
    attachment_bytes = await attachment.read()
    imagefileobj = await upscale_image(attachment_bytes)
    file = discord.File(imagefileobj, filename="image.png")
    embed = discord.Embed(color=discord.Color.blue())
    embed.add_field(name=current_language['upscale_warning'], inline=False)
    embed.set_image(url="attachment://image.png")
    await ctx.send(embed=embed, file=file)

@bot.hybrid_command(name="describe", description=current_language['describe'])
async def discribe(ctx, attachment: discord.Attachment):
    await ctx.defer()
    if not attachment.content_type.startswith('image/'):
        await ctx.send(current_language["image_error"])
        return
    attachment_bytes = await attachment.read()
    first_prompt = await generate_caption(attachment_bytes)
    second_prompt = await remix_prompt(first_prompt)
    third_prompt = await remix_prompt(first_prompt)
    fourth_prompt = await remix_prompt(first_prompt)
    embed = discord.Embed(description=f":one: {first_prompt}\n\n:two: {second_prompt}\n\n:three: {third_prompt}\n\n:four: {fourth_prompt}")
    embed.set_image(url=attachment.url)
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="remove-bg", description=current_language["remove-bg"])
async def removebg(ctx, attachment: discord.Attachment):
    await ctx.defer()
    if not attachment.content_type.startswith('image/'):
        await ctx.send(current_language["image_error"])
        return
    
    imagefileobj = await remove_image_bg(attachment.url)
    file = discord.File(imagefileobj, filename="image.png")
    embed = discord.Embed(title=current_language["remove-bg_msg"])
    embed.set_thumbnail(url=attachment.url)
    embed.set_image(url="attachment://image.png")
    
    await ctx.send(embed=embed, file=file)

@bot.hybrid_command(name="gif", description=current_language["nekos"])
@app_commands.choices(category=[
    app_commands.Choice(name=category.capitalize(), value=category)
    for category in ['baka', 'bite', 'blush', 'bored', 'cry', 'cuddle', 'dance', 'facepalm', 'feed', 'handhold', 'happy', 'highfive', 'hug', 'kick', 'kiss', 'laugh', 'nod', 'nom', 'nope', 'pat', 'poke', 'pout', 'punch', 'shoot', 'shrug']
])
async def gif(ctx, category: app_commands.Choice[str]):
    base_url = "https://nekos.best/api/v2/"

    url = base_url + category.value

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                await ctx.channel.send("Failed to fetch the image.")
                return

            json_data = await response.json()

            results = json_data.get("results")
            if not results:
                await ctx.channel.send("No image found.")
                return

            image_url = results[0].get("url")

            embed = Embed(colour=0x141414)
            embed.set_image(url=image_url)
            await ctx.send(embed=embed)

@bot.hybrid_command(name="translate", description="Translate text to english")
async def translate(ctx, *, text):
    await ctx.defer()
    translated = await translate_to_en(text)
    embed = discord.Embed(
        title="Translation",
        description=translated,
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

bot.remove_command("help")
@bot.hybrid_command(name="help", description=current_language["help"])
async def help(ctx):
    embed = discord.Embed(title="Bot Commands", color=0x03a64b)
    embed.set_thumbnail(url=bot.user.avatar.url)
    command_tree = bot.commands
    for command in command_tree:
        if command.hidden:
            continue
        command_description = command.description or current_language["help_cmd_err"]
        embed.add_field(name=command.name,
                        value=command_description, inline=False)

    embed.set_footer(text=f"{current_language['help_footer']}")

    await ctx.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(f"{ctx.author.mention} {current_language['command_err_admin']}")
    elif isinstance(error, commands.NotOwner):
        await ctx.send(f"{ctx.author.mention} {current_language['command_err_owner']}")

if detect_replit():
    from utilities.replit_flask_runner import run_flask_in_thread
    run_flask_in_thread()
    
if __name__ == "__main__":
    bot.run(TOKEN)