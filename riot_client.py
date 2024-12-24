import os
import requests
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
from collections import Counter
from firebase_admin import db 
from config import firebase_config # import to initialize db
import re
from flask import session

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
    global_region = PLATFORM_TO_GLOBAL.get(region, "americas")
    url = f"https://{global_region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
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


def get_user_match_details(puuid, match_id, region="na1"):
    """
    Fetch detailed match information for a specific match filtered by the user's PUUID,
    and calculate the average rank of the lobby.
    """
    global_region = PLATFORM_TO_GLOBAL.get(region, "americas")  # Use regional routing for match details
    platform_region = region 
    url = f"https://{global_region}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    headers = {"X-Riot-Token": RIOT_API_KEY}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        match_data = response.json()

        # Filter out non-Ranked Solo/Duo matches
        game_mode = match_data["info"].get("gameMode", "")
        if game_mode != "CLASSIC":
            print(f"Skipping non-Ranked Solo/Duo match: {match_id} with gameMode: {game_mode}")
            return None

        # Locate the participant data for the given PUUID
        participants = match_data["info"]["participants"]
        user_participant = next((p for p in participants if p["puuid"] == puuid), None)

        if not user_participant:
            print(f"No participant found for PUUID {puuid} in match {match_id}.")
            return None

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
            "game_mode": game_mode,
            "game_duration": match_data["info"].get("gameDuration", 0) // 60,  # Convert seconds to minutes
            "game_start_timestamp": game_start_timestamp,  # Include gameStartTimestamp
            "game_time_ago": game_time_ago,
            "user_data": {
                "championName": champion_name,
                "champion_icon": champion_icon,
                "puuid" : puuid,
                "kills": user_participant.get("kills", 0),
                "deaths": user_participant.get("deaths", 0),
                "assists": user_participant.get("assists", 0),
                "totalCS": total_cs,  # Corrected CS calculation
                "win": user_participant.get("win", False),
            },
        }
        return match_details

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


def get_ranked_stats_by_summoner_id(summoner_id, platform_region="na1"):
    """
    Fetch ranked stats for a summoner by their encrypted summoner ID.
    """
    url = f"https://{platform_region}.api.riotgames.com/lol/league/v4/entries/by-summoner/{summoner_id}"
    headers = {"X-Riot-Token": RIOT_API_KEY}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        ranked_stats = response.json()
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
        return f"{time_difference.days} day{'s' if time_difference.days > 1 else ''} ago"
    elif time_difference.seconds >= 3600:
        hours = time_difference.seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif time_difference.seconds >= 60:
        minutes = time_difference.seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    else:
        return "Less than a minute ago"
    
    
def get_mmr_estimate(game_name, tag_line, region="na1"):
    account_info = get_account_by_riot_id(game_name, tag_line, region)
    if not account_info:
        return "Error: Account not found"
    
    summoner_puuid = account_info.get("puuid")
    summoner_info = get_summoner_info_by_puuid(summoner_puuid, region)
    summoner_id = summoner_info.get("id")
    ranked_stats = get_ranked_stats_by_summoner_id(summoner_id, region)
    if not ranked_stats:
        return "Error: Ranked stats not found"
    
    # Get both the rank and the division
    rank = ranked_stats[0].get('tier', 'IRON') + " " + ranked_stats[0].get('rank', 'IV')
    lp = ranked_stats[0].get('leaguePoints', 0)
    
    # Estimate MMR from rank and LP
    estimated_mmr = estimate_mmr_from_rank_and_lp(rank, lp)
    
    # Calculate performance metrics (win rate, KDA, CS)
    match_history = session.get("match_history", [])
    print("Match History Retrieved in get_mmr_estimate:", match_history)
    print("Match History Passed to Metrics Calculation:", match_history)
    performance_metrics = calculate_performance_metrics(match_history, summoner_puuid, region)
    print("Calculated Performance Metrics:", performance_metrics)
    
    return {
        "estimated_mmr": estimated_mmr,
        "rank_label": get_rank_by_mmr(estimated_mmr),  # This is used for the rank label next to the MMR
        "win_rate": performance_metrics["win_rate"],
        "kda": performance_metrics["kda"],
        "average_cs": performance_metrics["average_cs"]
    }


def get_match_history(puuid, region="americas", count=20):
    """Fetch match history"""
    url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    response = requests.get(url, headers=headers, params={"count": count})
    return response.json() if response.status_code == 200 else []


def calculate_performance_metrics(match_ids, puuid, region="americas"):
    """Calculate win rate, KDA, and CS from the user's matches."""
    wins = 0
    total_kills = 0
    total_deaths = 0
    total_assists = 0
    total_cs = 0
    total_matches = 0

    for match_id in match_ids:
        match_details = get_user_match_details(puuid, match_id, region)
        if not match_details or "user_data" not in match_details:
            print(f"Skipping invalid or irrelevant match: {match_id}")
            continue

        user_data = match_details["user_data"]
        total_matches += 1
        if user_data["win"]:
            wins += 1
        total_kills += user_data.get("kills", 0)
        total_deaths += user_data.get("deaths", 0)
        total_assists += user_data.get("assists", 0)
        total_cs += user_data.get("totalCS", 0)

    win_rate = (wins / total_matches) * 100 if total_matches > 0 else 0
    kda = (total_kills + total_assists) / total_deaths if total_deaths > 0 else total_kills + total_assists
    average_cs = total_cs / total_matches if total_matches > 0 else 0

    return {
        "win_rate": round(win_rate, 2),
        "kda": round(kda, 2),
        "average_cs": round(average_cs, 2)
    }


def estimate_mmr_from_rank_and_lp(rank, lp):
    """Estimate MMR based on rank and LP"""
    rank_to_mmr = {
        'IRON IV': (1, 100),
        'IRON III': (101, 200),
        'IRON II': (201, 300),
        'IRON I': (301, 400),
        
        'BRONZE IV': (401, 500),
        'BRONZE III': (501, 600),
        'BRONZE II': (601, 700),
        'BRONZE I': (701, 800),
        
        'SILVER IV': (801, 900),
        'SILVER III': (901, 1000),
        'SILVER II': (1001, 1100),
        'SILVER I': (1101, 1200),
        
        'GOLD IV': (1201, 1300),
        'GOLD III': (1301, 1400),
        'GOLD II': (1401, 1500),
        'GOLD I': (1501, 1600),
        
        'PLATINUM IV': (1601, 1700),
        'PLATINUM III': (1701, 1800),
        'PLATINUM II': (1801, 1900),
        'PLATINUM I': (1901, 2000),
        
        'EMERALD IV': (2001, 2100),
        'EMERALD III': (2101, 2200),
        'EMERALD II': (2201, 2300),
        'EMERALD I': (2301, 2400),
        
        'DIAMOND IV': (2401, 2500),
        'DIAMOND III': (2501, 2600),
        'DIAMOND II': (2601, 2700),
        'DIAMOND I': (2701, 2800),
        
        'MASTER': (2801, 3200),
        
        'GRANDMASTER': (3201, 3600),
        
        'CHALLENGER': (3601, 4000)
    }

    # Retrieve rank range from the dictionary
    rank_lower, rank_upper = rank_to_mmr.get(rank.upper(), (None, None))
    
    # Check if the rank exists in the dictionary, if not return an error
    if rank_lower is None or rank_upper is None:
        print(f"Error: Rank {rank} not found in rank_to_mmr dictionary.")
        return 0  # Return 0 for invalid rank
    
    # Correctly calculate MMR from LP within the rank range
    estimated_mmr = rank_lower + (lp // 100)
    
    return estimated_mmr


def get_rank_by_mmr(mmr):
    """Find the rank based on MMR value"""
    rank_to_mmr = {
        'IRON IV': (1, 100),
        'IRON III': (101, 200),
        'IRON II': (201, 300),
        'IRON I': (301, 400),
        
        'BRONZE IV': (401, 500),
        'BRONZE III': (501, 600),
        'BRONZE II': (601, 700),
        'BRONZE I': (701, 800),
        
        'SILVER IV': (801, 900),
        'SILVER III': (901, 1000),
        'SILVER II': (1001, 1100),
        'SILVER I': (1101, 1200),
        
        'GOLD IV': (1201, 1300),
        'GOLD III': (1301, 1400),
        'GOLD II': (1401, 1500),
        'GOLD I': (1501, 1600),
        
        'PLATINUM IV': (1601, 1700),
        'PLATINUM III': (1701, 1800),
        'PLATINUM II': (1801, 1900),
        'PLATINUM I': (1901, 2000),
        
        'EMERALD IV': (2001, 2100),
        'EMERALD III': (2101, 2200),
        'EMERALD II': (2201, 2300),
        'EMERALD I': (2301, 2400),
        
        'DIAMOND IV': (2401, 2500),
        'DIAMOND III': (2501, 2600),
        'DIAMOND II': (2601, 2700),
        'DIAMOND I': (2701, 2800),
        
        'MASTER': (2801, 3200),
        
        'GRANDMASTER': (3201, 3600),
        
        'CHALLENGER': (3601, 4000)
    }

    # Iterate through the rank_to_mmr dictionary to find the correct division
    for rank, (min_mmr, max_mmr) in rank_to_mmr.items():
        if min_mmr <= mmr <= max_mmr:
            return f"({rank})"
    
    return "Unranked"  # Return Unranked if MMR doesn't match any rank


def sanitize_user_id(user_id):
    """
    Replace illegal characters in the user_id with an underscore.
    """
    return re.sub(r'[.#$[\]]', '_', user_id)


def save_user_data_to_realtime_db(
    user_id, mmr_data=None, match_history=None, stored_match_ids=None, 
    summoner_info=None, ranked_stats=None, most_played_champions=None
):
    """
    Save user data, including MMR, match history, and stored match IDs, to Realtime Database.
    """
    try:
        ref = db.reference(f"users/{sanitize_user_id(user_id)}")

        # Retrieve existing data to preserve fields like stored_match_ids
        existing_data = ref.get() or {}

        # Ensure summoner_info includes PUUID if available
        if match_history and "puuid" in match_history[0].get("user_data", {}):
            summoner_info = summoner_info or existing_data.get("summoner_info", {})
            summoner_info["puuid"] = match_history[0]["user_data"]["puuid"]

        # Default to existing data if parameters are not provided
        ranked_stats = ranked_stats or existing_data.get("ranked_stats", {})
        most_played_champions = most_played_champions or existing_data.get("most_played_champions", [])
        
        # Update match history with deduplication
        existing_match_history = existing_data.get("match_history", [])
        new_match_history = match_history or []
        combined_match_history = new_match_history + existing_match_history
        # Sort and limit to the 20 most recent matches
        combined_match_history = sorted(
            combined_match_history,
            key=lambda x: x.get("game_start_timestamp", 0),
            reverse=True
        )[:20]

        # Update stored match IDs
        existing_stored_ids = set(existing_data.get("stored_match_ids", []))
        new_stored_ids = set(stored_match_ids or [])
        updated_stored_ids = list(existing_stored_ids.union(new_stored_ids))

        # Update user data
        user_data = {
            "summoner_info": summoner_info or existing_data.get("summoner_info", {}),
            "ranked_stats": ranked_stats,
            "most_played_champions": most_played_champions,
            "mmr_data": mmr_data or existing_data.get("mmr_data", {}),
            "match_history": combined_match_history,
            "stored_match_ids": updated_stored_ids,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

        # Save data to the database
        ref.set(user_data)
        print(f"Data saved successfully for user: {user_id}")
    except Exception as e:
        print(f"Failed to save data to Realtime Database: {e}")


def fetch_initial_matches(puuid, region):
    ranked_match_details = []
    stored_match_ids = []
    start = 0

    while len(ranked_match_details) < 20:
        match_history = get_match_history_paged(puuid, start=start, count=20, region=PLATFORM_TO_GLOBAL[region])
        if not match_history:
            break

        for match_id in match_history:
            match_details = get_user_match_details(puuid, match_id, PLATFORM_TO_GLOBAL[region])
            if match_details and match_details.get("game_mode") == "CLASSIC":
                ranked_match_details.append(match_details)
                stored_match_ids.append(match_id)

                if len(ranked_match_details) == 20:
                    break

        start += 20

    return ranked_match_details, stored_match_ids


def initialize_user_portfolio(user_id, match_history):
    """
    Initialize the user's match portfolio in the database with the latest 20 matches.

    :param user_id: The unique user ID.
    :param match_history: List of match IDs to store initially.
    """
    ref = db.reference(f"users/{user_id}/matches")
    try:
        for match_id in match_history:
            ref.child(match_id).set({"stored": True})
        print(f"Initialized portfolio for user {user_id} with {len(match_history)} matches.")
    except Exception as e:
        print(f"Failed to initialize portfolio for user {user_id}: {e}")

def get_new_matches(user_id, fetched_match_history):
    """
    Identify new matches that are not already stored in the database.

    :param user_id: The unique user ID.
    :param fetched_match_history: List of match IDs fetched from the Riot API.
    :return: List of new match IDs.
    """
    ref = db.reference(f"users/{user_id}/matches")
    stored_matches = ref.get() or {}

    # Find matches that are not already stored
    new_matches = [match_id for match_id in fetched_match_history if match_id not in stored_matches]
    return new_matches

def append_new_matches(user_id, new_matches):
    """
    Append new matches to the user's portfolio in the database.

    :param user_id: The unique user ID.
    :param new_matches: List of new match IDs to add.
    """
    ref = db.reference(f"users/{user_id}/matches")
    try:
        for match_id in new_matches:
            ref.child(match_id).set({"stored": True})
        print(f"Appended {len(new_matches)} new matches to user {user_id}'s portfolio.")
    except Exception as e:
        print(f"Failed to append new matches for user {user_id}: {e}")

def save_match_to_database(user_id, match_id, match_details):
    """
    Save match details to the database.
    """
    try:
        ref = db.reference(f"users/{sanitize_user_id(user_id)}/matches/{match_id}")
        ref.set(match_details)
        print(f"Match {match_id} saved successfully for user {user_id}.")
    except Exception as e:
        print(f"Failed to save match {match_id} for user {user_id}: {e}")

def get_stored_match_ids(user_id):
    """
    Retrieve stored match IDs for a user.
    """
    ref = db.reference(f"users/{sanitize_user_id(user_id)}/matches")
    stored_matches = ref.get() or {}
    return set(stored_matches.keys())

def generate_weekly_dates():
    today = datetime.now()
    weeks = []

    print(f"Today's Date: {today.strftime('%Y-%m-%d')}")  # Debugging: Log today's date

    for i in range(10):
        date = today - timedelta(weeks=i)
        if not date:
            print(f"Invalid Date for Week {i + 1}")
            weeks.append("NaN.NaN")
            continue

        # Format the date as MM.DD
        formatted_date = date.strftime('%m.%d')
        weeks.append(formatted_date)


    return weeks[::-1]  # Return reversed for chronological order

def generate_daily_dates():
    today = datetime.now()
    days = []

    for i in range(12):
        date = today - timedelta(days=i)
        formatted_date = date.strftime('%m.%d')
        days.append(formatted_date)

    return days[::-1]

def roman_to_int(roman):
    """
    Converts a Roman numeral to an integer.
    Supports basic Roman numerals (e.g., I, II, III, IV).
    """
    roman_map = {'I': 1, 'V': 5, 'X': 10}
    result = 0
    prev_value = 0

    for char in reversed(roman):
        value = roman_map[char]
        if value < prev_value:
            result -= value
        else:
            result += value
        prev_value = value

    return result