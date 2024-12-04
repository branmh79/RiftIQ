from flask import Flask, request, jsonify, render_template
from riot_client import get_account_by_riot_id, get_match_history_paged, get_user_match_details, get_most_played_champions

app = Flask(__name__)

@app.route("/")
def home():
    return """
    <h1>Welcome to RiftIQ</h1>
    <form action="/search" method="post">
        <label for="game_name">Riot Game Name:</label>
        <input type="text" id="game_name" name="game_name" required>
        <br><br>
        <label for="tag_line">Tagline:</label>
        <input type="text" id="tag_line" name="tag_line" required>
        <br><br>
        <input type="submit" value="Search">
    </form>
    """

@app.route("/search", methods=["POST"])
def search():
    game_name = request.form["game_name"]
    tag_line = request.form["tag_line"]

    try:
        # Fetch summoner info
        summoner_info = get_account_by_riot_id(game_name, tag_line)
        if not summoner_info:
            raise Exception("Failed to fetch summoner information.")

        # Fetch initial match history (20 matches)
        match_history = get_match_history_paged(summoner_info["puuid"], start=0, count=20)
        if not match_history:
            raise Exception("Failed to fetch match history.")

        # Fetch user-specific match details
        user_match_details = []
        for match_id in match_history:
            details = get_user_match_details(summoner_info["puuid"], match_id)
            if details:
                user_match_details.append(details)

        # Calculate most-played champions
        most_played_champions = get_most_played_champions(user_match_details, summoner_info["puuid"])

        return render_template(
            "result.html",
            summoner_info=summoner_info,
            user_match_details=user_match_details,
            most_played_champions=most_played_champions
        )
    except Exception as e:
        return render_template("error.html", error=str(e)), 400

@app.route("/load_more", methods=["POST"])
def load_more_matches():
    game_name = request.json.get("game_name")
    tag_line = request.json.get("tag_line")
    start = int(request.json.get("start", 0))

    try:
        # Fetch summoner info
        summoner_info = get_account_by_riot_id(game_name, tag_line)
        if not summoner_info:
            raise Exception("Failed to fetch summoner information.")

        # Fetch additional match history
        match_history = get_match_history_paged(summoner_info["puuid"], start=start, count=20)
        user_match_details = []

        for match_id in match_history:
            details = get_user_match_details(summoner_info["puuid"], match_id)
            if details:
                user_match_details.append(details)

        return jsonify(user_match_details=user_match_details)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == "__main__":
    app.run(debug=True)
