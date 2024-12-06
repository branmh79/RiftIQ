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
            game_time_ago = calculate_time_ago(game_end_timestamp)
            
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
                "game_time_ago": game_time_ago,
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
    
    if time_difference.days >= 84:
        return "three months ago"
    elif time_difference.days >= 56:
        return "two months ago"
    elif time_difference.days >= 28:
        return "a month ago"
    elif time_difference.days > 0:
        return f"{time_difference.days} days ago"
    elif time_difference.seconds >= 3600:
        hours = time_difference.seconds // 3600
        return f"{hours} hours ago"
    else:
        minutes = time_difference.seconds // 60
        return f"{minutes} minutes ago"
    
    
def get_mmr_estimate(game_name, tag_line, region="na1"):
    account_info = get_account_by_riot_id(game_name, tag_line, region)
    if not account_info:
        return "Error: Account not found"
    
    summoner_puuid = account_info.get("puuid") # issue is that account_info returns puuid not id
    summoner_info = get_summoner_info_by_puuid(summoner_puuid, region)
    summoner_id = summoner_info.get("id")
    ranked_stats = get_ranked_stats_by_summoner_id(summoner_id, region)
    if not ranked_stats:
        return "Error: Ranked stats not found"
    
    # Estimate MMR from rank and LP
    rank = ranked_stats[0].get('tier', 'IRON')
    lp = ranked_stats[0].get('leaguePoints', 0)
    estimated_mmr = estimate_mmr_from_rank_and_lp(rank, lp)
    
    # Calculate performance metrics (win rate, KDA, CS)
    puuid = account_info.get("puuid")
    match_history = get_match_history(puuid, region)
    performance_metrics = calculate_performance_metrics(match_history, puuid, region)
    
    return {
        "estimated_mmr": estimated_mmr,
        "win_rate": performance_metrics["win_rate"],
        "kda": performance_metrics["kda"],
        "average_cs": performance_metrics["average_cs"]
    }   
    
def get_match_history(puuid, region="na1", count=20):
    """Fetch match history"""
    url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    response = requests.get(url, headers=headers, params={"count": count})
    return response.json() if response.status_code == 200 else []


def calculate_performance_metrics(match_ids, puuid, region="na1"):
    """Calculate win rate, KDA, and CS from match history"""
    wins = 0
    total_kills = 0
    total_deaths = 0
    total_assists = 0
    total_cs = 0
    total_matches = len(match_ids)
    
    for match_id in match_ids:
        match_details = get_user_match_details(puuid, match_id, region)
        if match_details:
            user_participant = next((p for p in match_details['info']['participants'] if p['puuid'] == puuid), None)
            if user_participant:
                if user_participant['win']:
                    wins += 1
                total_kills += user_participant['kills']
                total_deaths += user_participant['deaths']
                total_assists += user_participant['assists']
                total_cs += user_participant['totalMinionsKilled'] + user_participant['neutralMinionsKilled']
    
    # Calculate KDA and win rate
    win_rate = wins / total_matches if total_matches > 0 else 0
    kda = (total_kills + total_assists) / total_deaths if total_deaths > 0 else total_kills + total_assists
    average_cs = total_cs / total_matches if total_matches > 0 else 0
    
    return {
        "win_rate": win_rate,
        "kda": kda,
        "average_cs": average_cs
    }
    
def estimate_mmr_from_rank_and_lp(rank, lp):
    """Estimate MMR based on rank and LP"""
    rank_to_mmr = {
        'IRON': (0, 1000),
        'BRONZE': (1001, 1200),
        'SILVER': (1201, 1400),
        'GOLD': (1401, 1600),
        'PLATINUM': (1601, 1800),
        'DIAMOND': (1801, 2000),
        'MASTER': (2001, 2200),
        'GRANDMASTER': (2201, 2400),
        'CHALLENGER': (2401, 2600)
    }

    rank_lower, rank_upper = rank_to_mmr.get(rank.upper(), (0, 1000))
    return rank_lower + lp // 100  # Approximate MMR from LP within the rank range
