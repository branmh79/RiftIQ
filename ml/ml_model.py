import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score
import firebase_admin
from firebase_admin import credentials, db

# Initialize Firebase Admin if not already initialized
if not firebase_admin._apps:
    cred = credentials.Certificate("C:/Users/Brandon/OneDrive - University of North Georgia/Desktop/RiftIQ/config/serviceAccountKey.json")
    firebase_admin.initialize_app(cred, {
        "databaseURL": "https://riftiq-d9da8-default-rtdb.firebaseio.com"
    })

def get_user_data_from_database(user_id):
    """
    Retrieve user data (match_history and mmr_data) from the database.

    :param user_id: The ID of the user (e.g., Riot ID or unique key).
    :return: Dictionary containing user match history and MMR data.
    """
    ref = db.reference(f"users/{user_id}")
    user_data = ref.get()

    if not user_data:
        raise ValueError(f"No data found for user {user_id}")

    return user_data

def extract_features_and_labels(user_data):
    """
    Extract features and labels from user match data.

    :param user_data: Dictionary containing user match history and mmr data.
    :return: Features (X) and labels (y) as numpy arrays.
    """
    match_history = user_data.get("match_history", [])
    mmr_data = user_data.get("mmr_data", {})

    # Initialize lists for features and labels
    features = []
    labels = []

    for match in match_history:
        user_stats = match.get("user_data", {})
        features.append([
            user_stats.get("kills", 0),
            user_stats.get("deaths", 0),
            user_stats.get("assists", 0),
            user_stats.get("totalCS", 0),
            1 if user_stats.get("win", False) else 0  # Convert win to 1/0
        ])

    # Use the estimated MMR as the label
    estimated_mmr = mmr_data.get("estimated_mmr", None)
    if estimated_mmr:
        labels = [estimated_mmr] * len(features)

    # Convert to numpy arrays
    return np.array(features), np.array(labels)

def split_data(X, y, test_size=0.2, random_state=42):
    """
    Split features and labels into training and testing sets.

    :param X: Features.
    :param y: Labels.
    :param test_size: Proportion of data to reserve for testing.
    :param random_state: Random seed for reproducibility.
    :return: Training and testing sets.
    """
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=random_state)
    return X_train, X_test, y_train, y_test

def calculate_performance_score(user_stats, game_duration):
    """
    Calculate a performance score based on user match statistics.

    :param user_stats: Dictionary containing match metrics (kills, deaths, assists, CS, win).
    :param game_duration: Duration of the match in minutes.
    :return: Weighted performance score.
    """
    THRESHOLDS = {
        "kills": 6,
        "deaths": 5,
        "assists": 7,
        "cs_per_minute": 6.5,
    }

    score = 0

    # Calculate CS/min
    cs_per_minute = user_stats.get("totalCS", 0) / max(game_duration, 1)  # Avoid division by zero

    # Weighted contributions
    if user_stats.get("kills", 0) >= THRESHOLDS["kills"]:
        score += 4  # Good kills add 4 points
    else:
        score -= 2  # Low kills subtract 2 points

    if user_stats.get("deaths", 0) <= THRESHOLDS["deaths"]:
        score += 4  # Few deaths add 4 points
    else:
        score -= 4  # High deaths subtract 4 points

    if user_stats.get("assists", 0) >= THRESHOLDS["assists"]:
        score += 2  # High assists add 2 points

    if cs_per_minute >= THRESHOLDS["cs_per_minute"]:
        score += 2  # Good CS/min adds 2 points
    else:
        score -= 2  # Poor CS/min subtracts 2 points

    if user_stats.get("win", False):
        score += 6  # Winning adds 6 points

    return score

def get_baseline_mmr(displayed_rank):
    """
    Get the baseline MMR for a user's displayed rank.

    :param displayed_rank: User's displayed rank (e.g., "DIAMOND IV").
    :return: Baseline MMR value.
    """
    RANK_TO_MMR = {
        "IRON IV": 100, "IRON III": 200, "IRON II": 300, "IRON I": 400,
        "BRONZE IV": 500, "BRONZE III": 600, "BRONZE II": 700, "BRONZE I": 800,
        "SILVER IV": 900, "SILVER III": 1000, "SILVER II": 1100, "SILVER I": 1200,
        "GOLD IV": 1300, "GOLD III": 1400, "GOLD II": 1500, "GOLD I": 1600,
        "PLATINUM IV": 1700, "PLATINUM III": 1800, "PLATINUM II": 1900, "PLATINUM I": 2000,
        "DIAMOND IV": 2100, "DIAMOND III": 2200, "DIAMOND II": 2300, "DIAMOND I": 2400,
        "MASTER": 2500, "GRANDMASTER": 2800, "CHALLENGER": 3200
    }
    return RANK_TO_MMR.get(displayed_rank.upper(), None)

def calculate_precise_mmr(displayed_rank, performance_scores):
    """
    Calculate a precise MMR value based on displayed rank and performance scores.

    :param displayed_rank: User's displayed rank (e.g., "DIAMOND IV").
    :param performance_scores: List of performance scores for the user's matches.
    :return: Fine-tuned MMR value.
    """
    displayed_rank = displayed_rank.replace("(", "").replace(")", "").strip()
    
    baseline_mmr = get_baseline_mmr(displayed_rank)
    if baseline_mmr is None:
        raise ValueError(f"Invalid displayed rank: {displayed_rank}")

    # Average performance score
    avg_performance_score = sum(performance_scores) / len(performance_scores)

    # Fine-tune MMR (adjust by 10 points per performance score unit)
    precise_mmr = baseline_mmr + (avg_performance_score * 10)
    return round(precise_mmr)

if __name__ == "__main__":
    # Specify the user ID
    user_id = "bloo_buff"  # Replace with the actual user ID from your database

    # Fetch user data from the database
    user_data = get_user_data_from_database(user_id)

    # Extract features and calculate performance scores
    performance_scores = []
    for match in user_data["match_history"]:
        stats = match["user_data"]
        game_duration = stats.pop("game_duration", 1)  # Extract and remove game duration
        performance_scores.append(calculate_performance_score(stats, game_duration))

    # Calculate precise MMR
    displayed_rank = user_data["mmr_data"]["rank_label"]
    precise_mmr = calculate_precise_mmr(displayed_rank, performance_scores)

    print(f"Precise MMR for {user_id}: {precise_mmr}")
