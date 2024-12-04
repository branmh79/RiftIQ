from flask import Flask, request, jsonify, render_template
from riot_client import (
    PLATFORM_TO_GLOBAL,
    get_account_by_riot_id,
    get_match_history_paged,
    get_user_match_details,
    get_most_played_champions,
    get_summoner_ranked_stats,
    get_ranked_stats_by_summoner_id,
    get_summoner_info_by_puuid,
    get_riot_id_by_puuid
)

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/search", methods=["POST"])
def search():
    game_name = request.form["game_name"]
    tag_line = request.form["tag_line"]
    region = request.form.get("region", "na1")  # Default to NA1 if not specified

    try:
        # Fetch account info
        account_info = get_account_by_riot_id(game_name, tag_line)
        print("Account Info:", account_info)

        if not account_info or "puuid" not in account_info:
            raise Exception("Failed to fetch valid account information.")

        # Fetch summoner info by PUUID
        summoner_info = get_summoner_info_by_puuid(account_info["puuid"], region)
        print("Summoner Info:", summoner_info)

        if not summoner_info or "id" not in summoner_info:
            raise Exception("Failed to fetch valid summoner information.")

        # Fetch ranked stats
        all_ranked_stats = get_ranked_stats_by_summoner_id(summoner_info["id"], region)
        ranked_stats = next(
            (stats for stats in all_ranked_stats if stats["queueType"] == "RANKED_SOLO_5x5"), 
            None
        )

        # Fetch match history (initial 20 matches)
        match_history = get_match_history_paged(
            summoner_info["puuid"], 0, 20, PLATFORM_TO_GLOBAL[region]
        )

        # Fetch user-specific match details
        user_match_details = [
            get_user_match_details(summoner_info["puuid"], match_id, PLATFORM_TO_GLOBAL[region])
            for match_id in match_history
        ]

        # Calculate most played champions
        most_played_champions = get_most_played_champions(user_match_details, summoner_info["puuid"])

        return render_template(
            "result.html",
            riot_id={"gameName": game_name, "tagLine": tag_line},
            summoner_info=summoner_info,
            ranked_stats=ranked_stats,
            user_match_details=user_match_details,
            most_played_champions=most_played_champions,
        )
    except Exception as e:
        print("Error in search:", e)
        return render_template("error.html", error=str(e)), 400




@app.route("/load_more", methods=["POST"])
def load_more_matches():
    try:
        # Debug incoming request data
        data = request.json
        print("Incoming load_more request data:", data)

        game_name = data.get("game_name")
        tag_line = data.get("tag_line")
        start = int(data.get("start", 0))
        region = data.get("region", "na1").strip()  # Default to NA1 if no region is provided or it's empty

        # Check if any field is missing
        if not game_name or not tag_line:
            raise ValueError("Missing required parameters: game_name or tag_line")

        # Fetch summoner info by Riot ID
        riot_id = {"gameName": game_name, "tagLine": tag_line}
        print("Riot ID for load_more:", riot_id)

        account_info = get_account_by_riot_id(game_name, tag_line, region)
        if not account_info or "puuid" not in account_info:
            raise Exception("Failed to fetch valid account information.")

        puuid = account_info["puuid"]
        print("PUUID:", puuid)

        # Fetch additional match history
        region_route = PLATFORM_TO_GLOBAL.get(region, "na1")  # Default to "na1" if region is invalid
        match_history = get_match_history_paged(puuid, start=start, count=20, region=region_route)
        user_match_details = []

        for match_id in match_history:
            details = get_user_match_details(puuid, match_id, region_route)
            if details:
                user_match_details.append(details)

        return jsonify(user_match_details=user_match_details)
    except Exception as e:
        print("Error in load_more_matches:", e)
        return jsonify({"error": str(e)}), 400





if __name__ == "__main__":
    app.run(debug=True)
