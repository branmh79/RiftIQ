from flask import Flask, request, jsonify, render_template, session
from firebase_admin import credentials, db
from datetime import datetime, timezone
from riot_client import (
    PLATFORM_TO_GLOBAL,
    get_account_by_riot_id,
    get_match_history_paged,
    get_user_match_details,
    get_most_played_champions,
    get_ranked_stats_by_summoner_id,
    get_summoner_info_by_puuid,
    get_mmr_estimate,
    get_rank_by_mmr,
    save_user_data_to_realtime_db,
    calculate_performance_metrics,
    sanitize_user_id,
    save_match_to_database,
    get_stored_match_ids,
    fetch_initial_matches,
    calculate_time_ago
)

app = Flask(__name__)
app.secret_key = "supersecretkey"

@app.route("/")
def home():
    return render_template("home.html")


@app.route("/search", methods=["POST"])
def search():
    game_name = request.form["game_name"]
    tag_line = request.form["tag_line"]
    region = request.form.get("region", "na1")

    try:
        user_id = sanitize_user_id(f"{game_name}#{tag_line}")
        ref = db.reference(f"users/{user_id}")
        user_data = ref.get()

        if user_data:
            # Parse the last updated time
            last_updated_str = user_data.get("last_updated")
            last_updated = None
            if last_updated_str:
                try:
                    last_updated = datetime.fromisoformat(last_updated_str)
                except ValueError:
                    print(f"Invalid last_updated format: {last_updated_str}")

            # Calculate "time ago" for last updated
            last_updated_text = "Never"
            if last_updated:
                last_updated_text = calculate_time_ago(int(last_updated.timestamp() * 1000))
            
            # Existing user: Load matches from the database
            print(f"User {user_id} already exists. Loading from database.")
            match_history = user_data.get("match_history", [])[:20]  # Get only the latest 20 matches
            
            for match in match_history:
                if "game_start_timestamp" in match:
                    match["game_time_ago"] = calculate_time_ago(match["game_start_timestamp"])
                    
            return render_template(
                "result.html",
                riot_id={"gameName": game_name, "tagLine": tag_line},
                summoner_info=user_data.get("summoner_info", {}),
                ranked_stats=user_data.get("ranked_stats", {}),
                user_match_details=match_history,
                most_played_champions=user_data.get("most_played_champions", []),
                region=region,
                mmr_data=user_data.get("mmr_data", {}),
                rank=get_rank_by_mmr(user_data.get("mmr_data", {}).get("estimated_mmr", 0)),
                last_updated = last_updated_text,
            )

        # New user: Fetch matches from Riot API
        account_info = get_account_by_riot_id(game_name, tag_line, region)
        if not account_info or "puuid" not in account_info:
            raise Exception("Failed to fetch valid account information.")

        summoner_info = get_summoner_info_by_puuid(account_info["puuid"], region)
        if not summoner_info or "id" not in summoner_info:
            raise Exception("Failed to fetch valid summoner information.")

        ranked_stats = next(
            (
                stats
                for stats in get_ranked_stats_by_summoner_id(summoner_info["id"], region)
                if stats["queueType"] == "RANKED_SOLO_5x5"
            ),
            None,
        )

        # Fetch the latest 20 ranked matches
        puuid = account_info["puuid"]
        ranked_match_details, stored_match_ids = fetch_initial_matches(puuid, region)

        # Update the "time played ago" for each match
        for match in ranked_match_details:
            if "game_start_timestamp" in match:
                match["game_time_ago"] = calculate_time_ago(match["game_start_timestamp"])

        save_user_data_to_realtime_db(
            user_id=user_id,
            mmr_data=None,
            match_history=ranked_match_details,
            stored_match_ids=stored_match_ids,
            summoner_info=summoner_info,
            ranked_stats=ranked_stats,
            most_played_champions=get_most_played_champions(ranked_match_details, puuid),
        )

        return render_template(
            "result.html",
            riot_id={"gameName": game_name, "tagLine": tag_line},
            summoner_info=summoner_info,
            ranked_stats=ranked_stats,
            user_match_details=ranked_match_details,
            most_played_champions=get_most_played_champions(ranked_match_details, puuid),
            region=region,
            mmr_data=None,
            rank=None,
        )
    except Exception as e:
        print("Error in search:", e)
        return render_template("error.html", error=str(e)), 400


@app.route("/load_more", methods=["POST"])
def load_more_matches():
    try:
        user_id = request.json.get("user_id")
        start = int(request.json.get("start", 0))

        if not user_id:
            raise ValueError("User ID is required.")

        ref = db.reference(f"users/{sanitize_user_id(user_id)}/match_history")
        match_history = ref.get() or []

        # Check if there are more matches to load
        if start >= len(match_history):
            return jsonify({"message": "No more matches to load!"}), 200

        # Fetch the next batch of matches
        next_matches = match_history[start:start + 20]

        # Validate matches
        validated_matches = []
        for match in next_matches:
            if match and isinstance(match, dict) and "user_data" in match and match["user_data"]:
                validated_matches.append(match)
            else:
                print(f"Skipping invalid match data: {match}")

        # If no validated matches, return a message
        if not validated_matches:
            return jsonify({"message": "No more matches to load!"}), 200

        return jsonify({"matches": validated_matches})
    except Exception as e:
        print("Error in load_more_matches:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/refresh_matches", methods=["POST"])
def refresh_matches():
    try:
        user_id = request.json.get("user_id")
        if not user_id:
            return jsonify({"error": "User ID is required."}), 400

        ref = db.reference(f"users/{sanitize_user_id(user_id)}")
        user_data = ref.get()

        if not user_data:
            return jsonify({"error": "User not found. Please search first."}), 400

        stored_match_ids = set(user_data.get("stored_match_ids", []))
        puuid = user_data.get("summoner_info", {}).get("puuid")
        if not puuid:
            return jsonify({"error": "PUUID not found in user data."}), 400

        # Fetch recent matches
        new_match_ids = []
        match_history = get_match_history_paged(puuid, count=20, region=PLATFORM_TO_GLOBAL.get(request.json.get("region", "na1")))

        new_match_details = []
        for match_id in match_history:
            if match_id in stored_match_ids:
                break  # Stop at the first match already in stored_match_ids
            match_details = get_user_match_details(puuid, match_id, PLATFORM_TO_GLOBAL[request.json.get("region", "na1")])
            if match_details and match_details.get("game_mode") == "CLASSIC":
                match_details["game_time_ago"] = calculate_time_ago(match_details.get("game_start_timestamp"))
                new_match_ids.append(match_id)
                new_match_details.append(match_details)

        # Update the database
        last_updated = datetime.now(timezone.utc).isoformat()
        ref.child("last_updated").set(last_updated)
        if new_match_ids:
            stored_match_ids.update(new_match_ids)
            ref.child("stored_match_ids").set(list(stored_match_ids))
            ref.child("match_history").set(new_match_details + user_data.get("match_history", [])[:20])
            ref.child("last_updated").set(last_updated)

            return jsonify({
                "message": f"{len(new_match_ids)} new matches added!",
                "new_matches": new_match_ids,
                "last_updated": "just now"
            })

        # No new matches
        return jsonify({"message": "No new matches", "last_updated": "just now"})
    except Exception as e:
        print("Error in refresh_matches:", e)
        return jsonify({"error": str(e)}), 500



if __name__ == "__main__":
    app.run(debug=True)
