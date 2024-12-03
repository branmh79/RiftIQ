import os
import requests
from dotenv import load_dotenv  
from collections import Counter

# Load environment variables from .env file
load_dotenv()

# Fetch the Riot API key from .env file
RIOT_API_KEY = os.getenv("RIOT_API_KEY")

if not RIOT_API_KEY:
    raise Exception("Riot API key not found. Please add it to your .env file as RIOT_API_KEY.")

def get_account_by_riot_id(game_name, tag_line, region="americas"):
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


def get_match_history(puuid, region="americas", count=10, start=0):
    """
    Fetch match history with pagination.

    Args:
        puuid (str): The PUUID of the user.
        region (str): The region for the match endpoint.
        count (int): Number of matches to fetch.
        start (int): Start index for pagination.

    Returns:
        list: Match IDs.
    """
    url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
    headers = {
        "X-Riot-Token": RIOT_API_KEY
    }
    params = {
        "count": count,
        "start": start
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err} - {response.text}")
    except Exception as err:
        print(f"An error occurred: {err}")
    return None


def get_user_match_details(puuid, match_id, region="americas"):
    """
    Fetches detailed information for a specific match, filtered for the given user's PUUID.

    Args:
        puuid (str): The unique PUUID of the user.
        match_id (str): The match ID to fetch details for.
        region (str): The region for the match endpoint (default: "americas").

    Returns:
        dict: User-specific match details, or None if the request fails.
    """
    url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    headers = {
        "X-Riot-Token": RIOT_API_KEY
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        match_data = response.json()

        # Extract only the participant details for the given PUUID
        user_participant = next(
            (participant for participant in match_data["info"]["participants"] if participant["puuid"] == puuid), None
        )

        if user_participant:
            return {
                "match_id": match_id,
                "game_mode": match_data["info"]["gameMode"],
                "game_duration": match_data["info"]["gameDuration"] // 60,
                "user_data": user_participant,
            }
        else:
            print(f"User with PUUID {puuid} not found in match {match_id}.")
            return None
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err} - {response.text}")
    except Exception as err:
        print(f"An error occurred: {err}")
    return None

def get_most_played_champions(match_history, summoner_puuid):
    """
    Analyzes match history and returns the most played champions with winrate and games played.
    """
    from collections import Counter

    champion_stats = Counter()
    champion_wins = Counter()

    for match in match_history:
        # Ensure 'user_data' is correctly accessed
        participant = match.get("user_data", {})
        if not participant:
            continue  # Skip if 'user_data' is missing

        champion_name = participant.get("championName")
        if not champion_name:
            continue  # Skip if championName is missing

        champion_stats[champion_name] += 1
        if participant.get("win"):
            champion_wins[champion_name] += 1

    most_played = []
    for champion, games in champion_stats.most_common(5):  # Top 5 champions
        wins = champion_wins[champion]
        winrate = round((wins / games) * 100, 2)
        most_played.append({
            "champion": champion,
            "games_played": games,
            "winrate": f"{winrate}%",
        })

    return most_played
