import re
import random
import aiohttp
from langdetect import detect
import re
import aiohttp

async def replace_gif_search_query(text):
    """
        Replaces the search query in the given text with a GIF URL.

        Args:
            text (str): The input text containing the search query.

        Returns:
            str: The text with the search query replaced by the corresponding GIF URL, if found. 
                Otherwise, the original text is returned.
    """
    pattern = r'<q=(.*?)>'
    match = re.search(pattern, text)
    
    if match:
        search_query = match.group(1)
        url = f"https://gif-api.mishal0legit.repl.co/search?q={search_query}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    gif_url = data["gif_url"]
                    replaced_text = text.replace(f"<q={search_query}>", gif_url)
                    return replaced_text
    
    return text

async def search_gif_query(query):
    """
    An asynchronous function that takes in a query parameter and searches for a GIF based on the query.
    
    :param query: A string representing the search query.
    :return: A string representing the URL of the GIF.
    """
    url = f"https://gif-api.mishal0legit.repl.co/search?q={query}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
            gif_url = data["gif_url"]
            return gif_url
                
async def get_random_image_url(query):
    """
    Retrieves a random image URL based on the given query.

    Parameters:
        query (str): The query string used to search for images.

    Returns:
        str or None: A random image URL if successful, or None if no images were found or an error occurred.
    """
    encoded_query = aiohttp.helpers.quote(query)
    url = f'https://ddmm.ai/api/gsearch/a/{encoded_query}'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                json_data = await response.json()
                images_results = json_data.get("images_results", [])
                if images_results:
                    original_urls = [result["original"] for result in images_results]
                    random_original_url = random.choice(original_urls)
                    return random_original_url
            else:
                return None
    return None

def split_response(response, max_length=1999):
    """
    Splits a response into chunks of text that are within a maximum length.

    Args:
        response (str): The response to be split into chunks.
        max_length (int, optional): The maximum length of each chunk. Defaults to 1999.

    Returns:
        list[str]: A list of chunks, where each chunk is a string of text within the maximum length.
    """
    lines = response.splitlines()
    chunks = []
    current_chunk = ""

    for line in lines:
        if len(current_chunk) + len(line) + 1 > max_length:
            chunks.append(current_chunk.strip())
            current_chunk = line
        else:
            if current_chunk:
                current_chunk += "\n"
            current_chunk += line

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks

async def translate_to_en(text):
    """
        Translates the given text to English.

        Args:
            text (str): The text to be translated.

        Returns:
            str: The translated text in English.
    """
    detected_lang = detect(text)
    if detected_lang == "en":
        return text
    API_URL = "https://api.pawan.krd/gtranslate"
    async with aiohttp.ClientSession() as session:
        async with session.get(API_URL, params={"text": text,"from": detected_lang,"to": "en",}) as response:
            data = await response.json()
            translation = data.get("translated")
            return translation

async def get_random_prompt(prompt):
    """
    Asynchronously retrieves a random prompt from an API based on the given `prompt`.

    Args:
        prompt (str): The input prompt.

    Returns:
        str: A randomly selected prompt from the API if the response status is 200,
            otherwise returns the input prompt.
    """
    url = 'https://lexica.art/api/infinite-prompts'
    headers = {
        'authority': 'lexica.art',
        'accept': 'application/json, text/plain, */*',
        'content-type': 'application/json',
        'dnt': '1',
        'origin': 'https://lexica.art',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36'
    }
    data = {
        'text': prompt,
        'searchMode': 'images',
        'source': 'search',
        'cursor': 0,
        'model': 'lexica-aperture-v2'
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as response:
            if response.status == 200:
                response_json = await response.json()
                prompts = response_json['prompts']
                random_prompt = random.choice(prompts)
                return random_prompt['prompt']
            else:
                return prompt