import os
import requests
from dotenv import load_dotenv
from time import sleep
from datetime import datetime, timezone
from collections import Counter

PLATFORM_TO_GLOBAL = {
    "na1": "americas",
    "br1": "americas",
    "la1": "americas",
    "la2": "americas",
    "euw1": "europe",
    "eun1": "europe",
    "tr1": "europe",
    "ru": "europe",
    "kr": "asia",
    "jp1": "asia",
    "oc1": "sea",
}


season_start_date = datetime(2024, 9, 25)
season_start_timestamp = int(season_start_date.timestamp() * 1000)

# Load environment variables
load_dotenv()
RIOT_API_KEY = os.getenv("RIOT_API_KEY")

if not RIOT_API_KEY:
    raise Exception("Riot API key not found. Please add it to your .env file as RIOT_API_KEY.")


def get_account_by_riot_id(game_name, tag_line, region="na1"):
    """
    Fetch account information using Riot ID (gameName + tagLine).
    """
    global_region = PLATFORM_TO_GLOBAL.get(region, "americas")  # Default to americas if region is not mapped
    url = f"https://{global_region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    headers = {"X-Riot-Token": RIOT_API_KEY}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        account_data = response.json()
        print("Account Info Response:", account_data)  # Debug output
        return account_data
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

        # Locate the participant data for the given PUUID
        user_participant = next(
            (p for p in match_data["info"]["participants"] if p["puuid"] == puuid), None
        )

        if user_participant:
            # Format champion name and retrieve champion icon URL
            champion_name = user_participant.get("championName", "Unknown")
            champion_icon = get_champion_icon(champion_name)

            # Safe access to game_start_timestamp and game_end_timestamp
            game_start_timestamp = match_data["info"].get("gameStartTimestamp", None)
            game_end_timestamp = match_data["info"].get("gameEndTimestamp", None)
            
            total_minions_killed = user_participant.get("totalMinionsKilled", 0)
            neutral_minions_killed = user_participant.get("neutralMinionsKilled", 0)

            # Sum lane minions and neutral minions for total CS
            total_cs = total_minions_killed + neutral_minions_killed

            # Construct match details
            match_details = {
                "match_id": match_id,
                "game_mode": match_data["info"].get("gameMode", "Unknown"),
                "game_duration": match_data["info"].get("gameDuration", 0) // 60,  # Convert seconds to minutes
                "game_start_timestamp": game_start_timestamp,  # Include gameStartTimestamp
                "user_data": {
                    "championName": champion_name,
                    "champion_icon": champion_icon,
                    "kills": user_participant.get("kills", 0),
                    "deaths": user_participant.get("deaths", 0),
                    "assists": user_participant.get("assists", 0),
                    "totalCS": total_cs,  # Corrected CS calculation
                    "win": user_participant.get("win", False),
                },
            }
            return match_details
        else:
            print(f"No participant found for PUUID {puuid} in match {match_id}.")
            return None

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err} - {response.text}")
    except Exception as err:
        print(f"An error occurred: {err}")
    return None








def get_most_played_champions(match_details, puuid):
    """
    Calculate the most played champions with win rates based on the match details.
    This will return the top 6 champions by games played, considering only the current season.
    """
    from collections import Counter

    champion_stats = Counter()
    champion_wins = Counter()

    # Filter out matches before the current season (Sept 25, 2024)
    for match in match_details:
        match_start_timestamp = match.get("game_start_timestamp")  # gameStartTimestamp is used here
        if match_start_timestamp and match_start_timestamp >= season_start_timestamp:  # Filter by season start
            participant = match.get("user_data", {})
            if participant:
                champion_name = participant.get("championName")
                champion_stats[champion_name] += 1
                if participant.get("win"):
                    champion_wins[champion_name] += 1

    # Get the top 6 champions by games played
    most_played = [
        {
            "champion": champ,
            "games_played": count,
            "winrate": f"{round((champion_wins[champ] / count) * 100, 2)}%" if count > 0 else "0%"
        }
        for champ, count in champion_stats.most_common(6)
    ]
    return most_played




def get_summoner_ranked_stats(summoner_id, region="na1"):
    """
    Fetches the current rank and win/loss ratio for the summoner.

    Args:
        summoner_id (str): The encrypted summoner ID.
        region (str): The region for the league endpoint.

    Returns:
        dict: Ranked stats including rank, tier, and win/loss ratio.
    """
    url = f"https://{region}.api.riotgames.com/lol/league/v4/entries/by-summoner/{summoner_id}"
    headers = {"X-Riot-Token": RIOT_API_KEY}

    try:
        # Fetch data from Riot API
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        ranked_stats = response.json()

        # Debugging: Print the response for verification
        print("Ranked Stats API Response:", ranked_stats)

        # Look for ranked solo queue stats
        solo_queue_stats = next(
            (entry for entry in ranked_stats if entry.get("queueType") == "RANKED_SOLO_5x5"), None
        )

        if solo_queue_stats:
            return {
                "tier": solo_queue_stats.get("tier"),
                "rank": solo_queue_stats.get("rank"),
                "leaguePoints": solo_queue_stats.get("leaguePoints"),
                "wins": solo_queue_stats.get("wins"),
                "losses": solo_queue_stats.get("losses"),
            }
        else:
            # No solo queue stats available
            print("No ranked solo queue data found.")
            return None
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err} - {response.text}")
    except Exception as err:
        print(f"An error occurred: {err}")
    return None

def get_ranked_stats_by_summoner_id(summoner_id, region="na1"):
    """
    Fetch ranked stats for a summoner by their encrypted summoner ID.
    """
    url = f"https://{region}.api.riotgames.com/lol/league/v4/entries/by-summoner/{summoner_id}"
    headers = {"X-Riot-Token": RIOT_API_KEY}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        ranked_stats = response.json()
        print("Ranked Stats Response:", ranked_stats)  # Debugging
        return ranked_stats
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err} - {response.text}")
    except Exception as err:
        print(f"An error occurred: {err}")
    return None

def get_summoner_info_by_puuid(puuid, region="na1"):
    """
    Fetch summoner information using PUUID.
    """
    url = f"https://{region}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
    headers = {"X-Riot-Token": RIOT_API_KEY}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        summoner_data = response.json()
        print("Summoner Info Response:", summoner_data)  # Debug output
        return summoner_data
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err} - {response.text}")
    except Exception as err:
        print(f"An error occurred: {err}")
    return None


def get_riot_id_by_puuid(puuid, region="americas"):
    """
    Fetch Riot ID (gameName + tagLine) using the player's PUUID.

    Args:
        puuid (str): The player's PUUID.
        region (str): The account region (e.g., 'americas').

    Returns:
        dict: Contains 'gameName' and 'tagLine'.
    """
    url = f"https://{region}.api.riotgames.com/riot/account/v1/accounts/by-puuid/{puuid}"
    headers = {"X-Riot-Token": RIOT_API_KEY}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        riot_id_data = response.json()
        print("Riot ID Response:", riot_id_data)  # Debugging
        return riot_id_data
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err} - {response.text}")
    except Exception as err:
        print(f"An error occurred: {err}")
    return None


def get_champion_icon(champion_name):
    """
    Fetch the URL for a champion icon from Data Dragon.
    """
    # Replace with the current patch version
    patch_version = "14.23.1"
    # Format champion name for Data Dragon (e.g., special cases like "Fiddlesticks" -> "FiddleSticks")
    formatted_champion_name = champion_name.replace(" ", "").replace("'", "")
    return f"http://ddragon.leagueoflegends.com/cdn/{patch_version}/img/champion/{formatted_champion_name}.png"



def calculate_time_ago(game_end_timestamp):
    if not game_end_timestamp:
        return "Unknown"

    now = datetime.now(timezone.utc)
    game_time = datetime.fromtimestamp(game_end_timestamp / 1000, tz=timezone.utc)
    time_difference = now - game_time

    if time_difference.days > 0:
        return f"{time_difference.days} days ago"
    elif time_difference.seconds >= 3600:
        hours = time_difference.seconds // 3600
        return f"{hours} hours ago"
    else:
        minutes = time_difference.seconds // 60
        return f"{minutes} minutes ago"

def get_all_matches_since_season(puuid, region="americas", season_start_timestamp=None):
    """
    Fetch all match history for the user since the season start, using pagination.
    """
    all_matches = []
    start = 0
    count = 100  # Riot API supports 100 matches per request
    while True:
        # Fetch the match IDs
        match_ids = get_match_history_paged(puuid, start=start, count=count, region=region)
        
        if not match_ids:  # If no more matches are available, stop
            break

        # Fetch match details for each match
        for match_id in match_ids:
            match_details = get_user_match_details(puuid, match_id, region)
            
            if match_details:
                # Check if the match is from the current season
                game_start_timestamp = match_details.get("game_start_timestamp")
                if game_start_timestamp and game_start_timestamp >= season_start_timestamp:
                    all_matches.append(match_details)

        start += count  # Move to the next page of matches

    return all_matches
