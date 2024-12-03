import os
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Fetch the Riot API key from .env file
RIOT_API_KEY = os.getenv("RIOT_API_KEY")

if not RIOT_API_KEY:
    raise Exception("Riot API key not found. Please add it to your .env file as RIOT_API_KEY.")

def fetch_summoner_info(game_name, tag_line, region="americas"):
    """
    Fetches account details using the Riot ID (gameName and tagLine).

    Args:
        game_name (str): The name part of the Riot ID (e.g., "Faker").
        tag_line (str): The tag part of the Riot ID (e.g., "KR1").
        region (str): The region for the account endpoint (default: "americas").

    Returns:
        dict: Account information, or None if the request fails.
    """
    url = f"https://{region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    headers = {
        "X-Riot-Token": RIOT_API_KEY
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        print(f"Account details fetched successfully for {game_name}#{tag_line}.")
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err} - {response.text}")
    except Exception as err:
        print(f"An error occurred: {err}")
    return None
