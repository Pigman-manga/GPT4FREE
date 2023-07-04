import aiohttp

async def shorten_link(url):
    api_url = "https://gotiny.cc/"
    headers = {
        "Content-Type": "application/json",
    }
    data = {
        "input": url,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(api_url+"api", json=data, headers=headers) as response:
              result = await response.json()
              urlcode = result[0].get("code")
              return api_url + urlcode