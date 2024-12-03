from flask import Flask, request, render_template
from riot_client import fetch_summoner_info

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
        summoner_info = fetch_summoner_info(game_name, tag_line)
        return render_template("result.html", summoner_info=summoner_info)
    except Exception as e:
        return render_template("error.html", error=str(e)), 400

if __name__ == "__main__":
    app.run(debug=True)
