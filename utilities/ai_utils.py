import aiohttp
from urllib.parse import quote
import io
from datetime import datetime
import re
import random
import asyncio

from youtube_transcript_api import YouTubeTranscriptApi

from utilities.config_loader import load_current_language, config
from imaginepy import AsyncImagine, Style, Ratio, Model, Mode 


current_language = load_current_language()
internet_access = config['INTERNET_ACCESS']

base_url_1 = 'https://gpt4.gravityengine.cc'

base_urls = [base_url_1]


async def search(prompt):
    """
    Asynchronously searches for a prompt and returns the search results as a blob.

    Args:
        prompt (str): The prompt to search for.

    Returns:
        str: The search results as a blob.

    Raises:
        None
    """
    if "gif" in prompt.lower():
        return "User asked for a gif to send a gif you will use the format <q=(.*?)> for example to send a giga chad you will send <q=gigachad> you will never ever send `![Anime Girl Gif](https://tenor.com/view/anime-cute-girl-gif-22142830)` instead you will send `<q=Anime girl>` with no markdown syntax when asked for a gif."
    
    if not internet_access or len(prompt) > 200:
        return
    search_results_limit = config['MAX_SEARCH_RESULTS']

    url_match = re.search(r'(https?://\S+)', prompt)
    if url_match:
        search_query = url_match.group(0)
    else:
        search_query = await get_query(prompt)

    if search_query is not None and len(search_query) > 1000:
        return

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    blob = f"Search results for: '{search_query}' at {current_time}:\n"
    if search_query is not None:
        print(
            f"\033[1;32mSearching for '\033[1;33m{search_query}\033[1;32m' at {current_time} with {search_results_limit} results limit ...\033[0m")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://ddg-api.herokuapp.com/search',
                                       params={'query': search_query, 'limit': search_results_limit}) as response:
                    search = await response.json()
        except aiohttp.ClientError as e:
            print(f"An error occurred during the search request: {e}")
            return

        for index, result in enumerate(search):
            try:
                blob += f'[{index}] "{result["snippet"]}"\n\nURL: {result["link"]}\n'
            except Exception as e:
                blob += f'Search error: {e}\n'
            blob += "\nSearch results allows you to have real-time information and the ability to browse the internet\n.As the links were generated by the system rather than the user, please send a response along with the link if necessary.\n"
        return blob
    else:
        blob = "No search query is needed for a response"
    return blob


async def generate_response(instructions, search, history, filecontent):
    """
    Generate a response using OpenAI's chat completions API.

    :param instructions: The important instructions for generating the response.
    :type instructions: str
    :param search: The search results to include in the response. If None, the realtime search feature is disabled.
    :type search: str or None
    :param history: The chat history to include in the response.
    :type history: list
    :param filecontent: The content of the file sent by the user. If None, a default message is used.
    :type filecontent: str or None
    :return: The generated response.
    :rtype: str or None
    """
    max_retries = 1
    if filecontent is None:
        filecontent = 'No extra files sent.'
    if search is not None:
        search_results = search
    elif search is None:
        search_results = "Realtime Search feature is disabled to analyze user sent filecontent"

    endpoint = '/api/openai/v1/chat/completions'
    headers = {
        'Content-Type': 'application/json',
    }
    data = {
        'model': 'gpt-3.5-turbo-16k-0613',
        'temperature': 0.7,
        'messages': [
            {"role": "system", "name": "important_instructions",
                "content": instructions},
            *history,
            {"role": "system", "name": "realtime_internet_access",
                "content": search_results},
            {"role": "system", "name": "user_sent_file_contents", "content": filecontent}
        ]
    }

    for retry in range(max_retries + 1):
        for base_url in base_urls:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(base_url + endpoint, headers=headers, json=data) as response:
                        response_data = await response.json()
                        choices = response_data['choices']
                        if choices:
                            return choices[0]['message']['content']
                        else:
                            print(
                                f"There was an error. This is the response from the API: {response_data}")
            except aiohttp.ClientError as e:
                print(
                    f"\033[91mAn error occurred during the API request: {e} \n Response : {response_data}\033[0m")
            except KeyError as e:
                print(
                    f"\033[91mInvalid response received from the API: {e} \n Response : {response_data}\033[0m")
            except Exception as e:
                print(
                    f"\033[91mAn unexpected error occurred: {e} \n Response : {response_data} \033[0m")

        if retry < max_retries:
            print(f"Retrying request..")

    return None


async def generate_gpt4_response(message, temperature=0.7):
    """
    Generate a GPT-4 response based on the given message and temperature.
    
    Parameters:
        - message: The message to generate the response for.
            Type: str
            
        - temperature: The temperature value to control the randomness of the response.
            Type: float
            Default: 0.7
    
    Returns:
        The generated GPT-4 response as a string.
    """
    url = "https://chat.skailar.net/api/chat"

    payload = {
        "model": {
            "id": "gpt-4-0613",
            "name": "GPT-4",
            "maxLength": 24000,
            "tokenLimit": 8000
        },
        "messages": [
            {"role": "user", "content": message}
        ],
        "prompt": "Your response will be rendered in a discord message, include language hints when returning code like: ```py ...```, and use * or ** or > to create highlights",
        "temperature": temperature
    }
    headers = {
        'content-type': 'application/json'
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            response_text = await resp.text()
            return response_text


async def generate_chat_completion(messages):
    """
    Asynchronously generates a chat completion using the OpenAI API.

    Args:
        messages (List[dict]): A list of message dictionaries representing the chat conversation.

    Returns:
        str: The generated chat completion.

    Raises:
        None.

    """
    endpoint = '/api/openai/v1/chat/completions'
    headers = {
        'Content-Type': 'application/json',
    }
    data = {
        'model': 'gpt-3.5-turbo-16k-0613',
        'temperature': 0.7,
        'messages': messages,
        'max_tokens': 30
    }

    for base_url in base_urls:
        async with aiohttp.ClientSession() as session:
            async with session.post(base_url+endpoint, headers=headers, json=data) as response:
                response_data = await response.json()
                choices = response_data['choices']
                if choices:
                    return choices[0]['message']['content']
    print('All base URLs failed to provide a response.')
    return None


async def detect_nsfw(prompt):
    """
    Detects if an image to text prompt contains graphic sexual material or nudity.
    
    Args:
        prompt (str): The image to text prompt.
        
    Returns:
        bool: True if the prompt contains graphic sexual material or nudity, False otherwise.
    """
    instructions = """From now on, you are going to act as nsfw image to text prompt detector. If the following message s involves graphic sexual material or nudity, content respond with "1" else respond with "0" and nothing else
    
    also nagative prompt defines what should not be in the image"""
    messages = [
        {"role": "system", "content": instructions},
        {"role": "system", "name": "example_user",
            "content":  "a Girl, China, 20yo, HD, realistic, without dress, uncensored."},
        {"role": "system", "name": "example_assistant", "content":  "1"},
        {"role": "system", "name": "example_user",
            "content": "Woman in black bikini Beach hot weather european full view Unreal Engine 5 Color Grading Editorials"},
        {"role": "system", "name": "example_assistant", "content":  "1"},
        {"role": "system", "name": "example_user",
            "content": "beautiful anime k-pop idol"},
        {"role": "system", "name": "example_assistant", "content":  "0"},
        {"role": "user", "content": prompt}
    ]

    response = await generate_chat_completion(messages)
    if "1" in response.lower():
        return True
    else:
        return False


async def get_query(prompt):
    """
    An asynchronous function that takes a prompt as input and generates a query response.
    The function simulates a chat-based interaction with a search query AI. It takes a prompt
    message and uses it to generate a response by calling the `generate_chat_completion` function.
    If the response contains the word "false" (case-insensitive), the function returns None.
    Otherwise, it processes the response by removing the word "Query" and the colon, and returns
    the processed response. If the response is empty, the function also returns None.

    Parameters:
    - prompt: A string representing the user's prompt message.

    Returns:
    - A string containing the query response, or None if the response is empty or contains the word "false".
    """
    instructions = f""""IMPORTANT :From now on you are going to act as search query ai. If a message is not directly addressed to the second person, you will need to initiate a search query else assistent will respond with False nothing more and assistant must only help by returning a query"""
    messages = [
        {"role": "system", "name": "instructions", "content": instructions},
        {"role": "system", "name": "example_user",
            "content":  "Message : Who made you ?"},
        {"role": "system", "name": "example_assistant", "content":  "Query : False"},
        {"role": "system", "name": "example_user",
            "content":  "Message : Who won in 2022 fifa world cup"},
        {"role": "system", "name": "example_assistant",
            "content":  "Query : FIFA World Cup results 2022"},
        {"role": "system", "name": "example_user",
            "content":  "Message : Who are you ?"},
        {"role": "system", "name": "example_assistant", "content":  "Query : False"},
        {"role": "system", "name": "example_user",
            "content":  "Message : What is happening in ukraine"},
        {"role": "system", "name": "example_assistant",
            "content":  "Query : Ukraine military news today"},
        {"role": "system", "name": "example_user", "content": "Message : Hi"},
        {"role": "system", "name": "example_assistant", "content":  "Query : False"},
        {"role": "system", "name": "example_user",
            "content": "Message : How are you doing ?"},
        {"role": "system", "name": "example_assistant", "content":  "Query : False"},
        {"role": "system", "name": "example_user",
            "content": "Message : How to print how many commands are synced on_ready ?"},
        {"role": "system", "name": "example_assistant",
            "content":  "Query : Python code to print the number of synced commands in on_ready event"},
        {"role": "system", "name": "example_user",
            "content": "Message : Phần mềm diệt virus nào tốt nhất năm 2023"},
        {"role": "system", "name": "example_assistant",
            "content":  "Query : 8 Best Antivirus Software"},
        {"role": "user", "content": f"Message : {prompt}"}
    ]

    response = await generate_chat_completion(messages)
    if "false" in response.lower():
        return None
    response = response.replace("Query:", "").replace(
        "Query", "").replace(":", "")
    if response:
        return response
    else:
        return None


async def remix_prompt(prompt):
    """
    Asynchronously remixes a given prompt by generating a variation of prompts.

    Args:
        prompt (str): The original prompt to be remixed.

    Returns:
        str: The remixed prompt generated by the chat completion model.
    """
    instructions = """IMPORTANT : From now on you are going to act as image prompt remixer and create variation of prompts and nothing else"""
    messages = [
        {"role": "system", "name": "instructions", "content": instructions},
        {"role": "system", "name": "example_user", "content": "Prompt : a close up of a person with pink hair, realistic cute girl painting, cute anime girl portrait, realistic anime 3d style, realistic anime style at pixiv, photorealistic anime girl render, live2d virtual youtuber model, render of a cute 3d anime girl, kawaii realistic portrait, realistic anime art style, realistic young anime girl, anime girl portrait"},
        {"role": "system", "name": "example_assistant", "content": "Remixed prompt :  a woman with long hair standing in a city, wlop | artgerm, artgerm and ilya kushinov, stanley artgerm lau, artgerm. anime illustration, artgerm lau, wlop and artgerm, realistic anime style at pixiv, rossdraws global illumination, wlop rossdraws, art of wlop"},
        {"role": "system", "name": "example_user", "content": "Prompt : close up of a person with white hair, kaworu nagisa, ken kaneki, kaneki ken, discord pfp, shinji, evangelion style eyes, with curly black and silver hair, very cute robot zen, white-haired deity, white-haired, discord profile picture, white-haired, zerochan, intense white hair, takeuchi takashi"},
        {"role": "system", "name": "example_assistant",
            "content": "Remixed prompt : a couple of anime characters standing next to each other, visual novel cg, high detailed perfect faces, mihoyo art style, silver hair (ponytail), high detailed official artwork, official art, girls frontline cg, official character illustration, official artwork, from arknights, official illustration, nier:automata, visual novel key visual, nier automata, mihoyo"},
        {"role": "user",
            "content": "Prompt : a woman holding a rose in her hand, hua cheng, ( ( god king of ai art ) ), visual novel sprite, from arknights, holding a rose, ghailan!, holding a red rose, long silver hair with a flower, | | very very anime!!!, yaoi, dating app icon, attractive male deity, wlop : :, long white hair!!!"},
        {"role": "assistant", "content": "Remixed prompt : a woman with long white hair holding a rose, high detailed official artwork, official character art, visual novel cg, detailed crimson moon, 4k hd. snow white hair, character profile art, official character illustration, scarlet background, holding a red rose, extremely detailed goddess shot, from arknights, detailed character portrait, girls frontline cg, mihoyo art style"},
        {"role": "user", "content": f"Prompt : {prompt}"},
    ]
    response = await generate_chat_completion(messages)
    response = response.replace("Remixed prompt :", "").replace(
        "Remixed prompt", "").replace(":", "")
    return response


async def upscale_image(image_byte):
    """
    Upscales an image using AsyncImagine.

    Parameters:
        image_byte (bytes): The image byte data to be upscaled.

    Returns:
        io.BytesIO: The upscaled image data as a BytesIO object.
    """
    imagine = AsyncImagine()
    img_data = await imagine.upscale(image=image_byte)
    img_file = io.BytesIO(img_data)
    await imagine.close()
    return img_file

async def generate_image(image_prompt, model_value, style_value, ratio_value, negative, upscale, seed, cfg):
    """
    Asynchronously generates an image based on the given parameters.

    :param image_prompt: The prompt for generating the image.
    :type image_prompt: str
    :param model_value: The value representing the model to be used for generating the image.
    :type model_value: int
    :param style_value: The value representing the style of the generated image.
    :type style_value: str
    :param ratio_value: The value representing the ratio of the generated image.
    :type ratio_value: float
    :param negative: The negative values for image generation.
    :type negative: str
    :param upscale: Whether to upscale the generated image.
    :type upscale: bool
    :param seed: The seed value for generating the image.
    :type seed: int
    :param cfg: The configuration for generating the image.
    :type cfg: dict
    :return: The generated image file.
    :rtype: io.BytesIO or None
    """
    if negative is None:
        negative = "(nsfw:1.5),verybadimagenegative_v1.3, ng_deepnegative_v1_75t, (ugly face:0.8),cross-eyed,sketches, (worst quality:2), (low quality:2), (normal quality:2), lowres, normal quality, ((monochrome)), ((grayscale)), skin spots, acnes, skin blemishes, bad anatomy, DeepNegative, facing away, tilted head, {Multiple people}, lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worstquality, low quality, normal quality, jpegartifacts, signature, watermark, username, blurry, bad feet, cropped, poorly drawn hands, poorly drawn face, mutation, deformed, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, extra fingers, fewer digits, extra limbs, extra arms,extra legs, malformed limbs, fused fingers, too many fingers, long neck, cross-eyed,mutated hands, polar lowres, bad body, bad proportions, gross proportions, text, error, missing fingers, missing arms, missing legs, extra digit, extra arms, extra leg, extra foot, repeating hair"
    imagine = AsyncImagine()
    style_enum = Style[style_value]
    ratio_enum = Ratio[ratio_value]
    model_enum = Model[model_value]
    img_data = await imagine.sdprem(
        prompt=image_prompt,
        model=model_enum,
        style=style_enum,
        ratio=ratio_enum,
        seed=seed,
        negative=negative,
        cfg=cfg
    )
    if upscale:
        img_data = await imagine.upscale(content=img_data)

    try:
        img_file = io.BytesIO(img_data)
    except Exception as e:
        print(f"An error occurred while creating the in-memory image file: {e}")
        return None
    await imagine.close()
    print("finished image gen")
    return img_file

async def generate_image_prodia(prompt, model, sampler, seed, neg):
    """
    Generates an image using the Prodia API based on the given prompt, model, sampler, seed, and negative prompts.

    Parameters:
        prompt (str): The prompt for generating the image.
        model (str): The model to use for generating the image.
        sampler (str): The sampler to use for generating the image.
        seed (str): The seed for generating the image.
        neg (str): Optional. The negative prompts for generating the image. If not provided, default negative prompts will be used.

    Returns:
        io.BytesIO: The image file object generated by the Prodia API.
    """
    async def create_job(prompt, model, sampler, seed, neg):
        if neg is None:
            negative = "verybadimagenegative_v1.3, ng_deepnegative_v1_75t, (ugly face:0.8),cross-eyed,sketches, (worst quality:2), (low quality:2), (normal quality:2), lowres, normal quality, ((monochrome)), ((grayscale)), skin spots, acnes, skin blemishes, bad anatomy, DeepNegative, facing away, tilted head, {Multiple people}, lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worstquality, low quality, normal quality, jpegartifacts, signature, watermark, username, blurry, bad feet, cropped, poorly drawn hands, poorly drawn face, mutation, deformed, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, extra fingers, fewer digits, extra limbs, extra arms,extra legs, malformed limbs, fused fingers, too many fingers, long neck, cross-eyed,mutated hands, polar lowres, bad body, bad proportions, gross proportions, text, error, missing fingers, missing arms, missing legs, extra digit, extra arms, extra leg, extra foot, repeating hair',"
        else:
            negative = neg
        url = 'https://api.prodia.com/generate'
        params = {
            'new': 'true',
            'prompt': f'{quote(prompt)}',
            'model': model,
            'negative_prompt': f"{negative}",
            'steps': '80',
            'cfg': '9.5',
            'seed': f'{seed}',
            'sampler': sampler,
            'upscale': 'True',
            'aspect_ratio': 'square'
        }
        headers = {
            'authority': 'api.prodia.com',
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.6',
            'dnt': '1',
            'origin': 'https://app.prodia.com',
            'referer': 'https://app.prodia.com/',
            'sec-ch-ua': '"Brave";v="113", "Chromium";v="113", "Not-A.Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Linux"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'sec-gpc': '1',
            'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36',
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as response:
                data = await response.json()
                return data['job']
            
    job_id = await create_job(prompt, model, sampler, seed, neg)
    url = f'https://api.prodia.com/job/{job_id}'
    headers = {
        'authority': 'api.prodia.com',
        'accept': '*/*',
    }

    async with aiohttp.ClientSession() as session:
        while True:
            async with session.get(url, headers=headers) as response:
                json = await response.json()
                if json['status'] == 'succeeded':
                    async with session.get(f'https://images.prodia.xyz/{job_id}.png?download=1', headers=headers) as response:
                        content = await response.content.read()
                        img_file_obj = io.BytesIO(content)
                        return img_file_obj

async def generate_image_remix(image_byte, image_prompt, upscale, control_value):
    """
    Generate a remix of an image based on the provided image byte data, image prompt,
    upscale flag, and control value.

    Args:
        image_byte (bytes): The byte data of the input image.
        image_prompt (str): The prompt to guide the image generation.
        upscale (bool): Flag indicating whether to upscale the generated image.
        control_value (str): The control value for the image generation.

    Returns:
        io.BytesIO or None: The remix image file as an io.BytesIO object if successful,
        None otherwise.
    """
    imagine = AsyncImagine()
    control_enum = Mode[control_value]
    img_data = await imagine.controlnet(
        content=image_byte,
        prompt=image_prompt,
        mode=control_enum
    )
    if upscale:
        img_data = await imagine.upscale(content=img_data)
    try:
        img_file = io.BytesIO(img_data)
    except Exception as e:
        print("An error occurred while creating the in-memory image file:", e)
        return None
    return img_file

async def remove_image_bg(image_url):
    """
    Asynchronously removes the background of an image using the remove.bg API.

    Parameters:
        image_url (str): The URL of the image to be processed.

    Returns:
        io.BytesIO: A file-like object containing the image with the background removed.
    """
    url = 'https://www.rembg.pics/api/generate'
    headers = {
        'content-type': 'application/json',
    }
    payload = {
        'imageUrl': image_url
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=payload) as response:
                response.raise_for_status()
                data = await response.json(content_type=None)

            async with session.get(data) as image_response:
                image_content = await image_response.read()

            file_object = io.BytesIO(image_content)

            return file_object
        finally:
            await session.close()


async def generate_caption(image_bytes):
    """
    Generate a caption for an image.

    Args:
        image_bytes: A byte string representing the image.

    Returns:
        A string representing the generated caption.
    """
    imagine = AsyncImagine()
    text = await imagine.interrogator(content=image_bytes)
    return text

async def poly_image_gen(session, prompt):
    """
    Asynchronously generates an image based on a given prompt.

    Args:
        session (ClientSession): The session to use for making the HTTP request.
        prompt (str): The prompt for generating the image.

    Returns:
        io.BytesIO: An in-memory binary stream containing the generated image data.
    """
    seed = random.randint(1, 100000)
    image_url = f"https://image.pollinations.ai/prompt/{prompt}{seed}"
    async with session.get(image_url) as response:
        image_data = await response.read()
        image_io = io.BytesIO(image_data)
        return image_io


async def get_yt_transcript(message_content):
    """
    Asynchronously retrieves the transcript of a YouTube video based on the given message content.

    Args:
        message_content (str): The content of the message containing the YouTube video link.

    Returns:
        str: The summarized transcript of the YouTube video or None if no transcript is available.

    Raises:
        None

    """
    def extract_video_id(message_content):
        youtube_link_pattern = re.compile(
            r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})')
        match = youtube_link_pattern.search(message_content)
        return match.group(6) if match else None

    video_id = extract_video_id(message_content)
    if not video_id:
        return None

    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    first_transcript = next(iter(transcript_list), None)
    if not first_transcript:
        return None

    translated_transcript = first_transcript.translate('en')
    formatted_transcript = ". ".join(
        [f"{entry['start']} - {entry['text']}" for entry in translated_transcript.fetch()])

    response = f"""Summarize the following youtube video transcript into few short concise bullet points:
    
    {formatted_transcript}
    
    
    Please Provide a summary or additional information based on the content. Write the summary in {current_language['language_name']}"""

    return response
