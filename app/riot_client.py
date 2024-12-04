import os
import requests
from dotenv import load_dotenv
from time import sleep

# Load environment variables
load_dotenv()
RIOT_API_KEY = os.getenv("RIOT_API_KEY")

if not RIOT_API_KEY:
    raise Exception("Riot API key not found. Please add it to your .env file as RIOT_API_KEY.")

def get_account_by_riot_id(game_name, tag_line, region="americas"):
    """
    Fetch account information using Riot ID (game name and tagline).
    """
    url = f"https://{region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err} - {response.text}")
    except Exception as err:
        print(f"An error occurred: {err}")
    return None

def get_match_history_paged(puuid, start=0, count=20, region="americas"):
    """
    Fetch paged match history for the user.
    """
    url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    params = {"start": start, "count": count}

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err} - {response.text}")
    except Exception as err:
        print(f"An error occurred: {err}")
    return []

def get_user_match_details(puuid, match_id, region="americas"):
    """
    Fetch detailed match information for a specific match filtered by the user's PUUID.
    """
    url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    headers = {"X-Riot-Token": RIOT_API_KEY}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        match_data = response.json()

        user_participant = next(
            (p for p in match_data["info"]["participants"] if p["puuid"] == puuid), None
        )
        return {
            "match_id": match_id,
            "game_mode": match_data["info"]["gameMode"],
            "game_duration": match_data["info"]["gameDuration"] // 60,
            "user_data": user_participant,
        } if user_participant else None
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
    except Exception as err:
        print(f"An error occurred: {err}")
    return None

def get_most_played_champions(match_details, puuid):
    """
    Calculate the most played champions with win rates based on the match details.
    """
    from collections import Counter

    champion_stats = Counter()
    champion_wins = Counter()

    for match in match_details:
        participant = match.get("user_data", {})
        if participant:
            champion_name = participant.get("championName")
            champion_stats[champion_name] += 1
            if participant.get("win"):
                champion_wins[champion_name] += 1

    most_played = [
        {
            "champion": champ,
            "games_played": count,
            "winrate": f"{round((champion_wins[champ] / count) * 100, 2)}%"
        }
        for champ, count in champion_stats.most_common(5)
    ]
    return most_played
