"""
Steam Achievements Counter
--------------------------
Fetches all owned games with:
  - Total achievements available
  - Unlocked achievements (earned by the player)
  - Playtime (Steam stores this internally as minutes)

Requirements:
    pip install requests

Setup:
    1. Get your Steam API key at: https://steamcommunity.com/dev/apikey
    2. Find your Steam ID at: https://www.steamidfinder.com/
       (It's the long number, e.g. 76561198XXXXXXXXX)
    3. Make sure your Steam profile and game details are set to PUBLIC.
       (Steam > Profile > Edit Profile > Privacy Settings > set to Public)
"""

import csv
import requests
import sys
import time
from datetime import datetime

# ── Configuration ────────────────────────────────────────────────────────────
STEAM_API_KEY = "YOUR_API_KEY_HERE"      # Replace with your Steam API key
STEAM_ID      = "YOUR_STEAM_ID_HERE"     # Replace with your 64-bit Steam ID
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL = "https://api.steampowered.com"


def get_owned_games(api_key: str, steam_id: str) -> list[dict]:
    """Return a list of owned games with appid, name, and playtime_forever (minutes)."""
    url = f"{BASE_URL}/IPlayerService/GetOwnedGames/v1/"
    params = {
        "key": api_key,
        "steamid": steam_id,
        "include_appinfo": True,
        "include_played_free_games": True,
        "format": "json",
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    games = data.get("response", {}).get("games", [])
    return sorted(games, key=lambda g: g.get("name", "").lower())


def format_playtime(minutes: int) -> str:
    """Convert Steam's internal playtime_forever (minutes) to a h/m/s string."""
    h  = minutes // 60
    m  = minutes % 60
    s  = 0   # Steam only exposes minute-level granularity
    return f"{h}h {m:02d}m {s:02d}s"


def get_achievement_stats(api_key: str, steam_id: str, app_id: int) -> tuple[int | None, int | None]:
    """
    Return (total_achievements, unlocked_achievements) for a game.
    Returns (None, None) if the game has no achievements or the data is unavailable.
    Steam's GetPlayerAchievements returns every achievement with an 'achieved' field
    set to 1 (unlocked) or 0 (locked).
    """
    url = f"{BASE_URL}/ISteamUserStats/GetPlayerAchievements/v1/"
    params = {
        "key": api_key,
        "steamid": steam_id,
        "appid": app_id,
        "format": "json",
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 400:
            return None, None  # Game has no achievements
        resp.raise_for_status()
        data = resp.json()
        achievements = data.get("playerstats", {}).get("achievements", [])
        if not achievements:
            return None, None
        total    = len(achievements)
        unlocked = sum(1 for a in achievements if a.get("achieved") == 1)
        return total, unlocked
    except requests.RequestException:
        return None, None


def main():
    # Basic config validation
    if "YOUR_API_KEY_HERE" in STEAM_API_KEY or "YOUR_STEAM_ID_HERE" in STEAM_ID:
        print("ERROR: Please set your STEAM_API_KEY and STEAM_ID in the script.")
        print("  - API Key : https://steamcommunity.com/dev/apikey")
        print("  - Steam ID: https://www.steamidfinder.com/")
        sys.exit(1)

    print("Fetching your Steam library...\n")

    try:
        games = get_owned_games(STEAM_API_KEY, STEAM_ID)
    except requests.HTTPError as e:
        print(f"Failed to fetch games: {e}")
        print("Check that your API key and Steam ID are correct, and your profile is public.")
        sys.exit(1)

    if not games:
        print("No games found. Make sure your profile and game library are set to Public.")
        sys.exit(0)

    print(f"Found {len(games)} game(s) in your library. Fetching data...\n")
    print(f"{'#':<5} {'Game':<45} {'Playtime':>14} {'Unlocked':>9} {'Total':>7}")
    print("-" * 84)

    results = []
    for i, game in enumerate(games, 1):
        name     = game.get("name", f"App {game['appid']}")
        app_id   = game["appid"]
        # Steam stores playtime_forever in minutes
        minutes  = game.get("playtime_forever", 0)
        playtime = format_playtime(minutes)

        total, unlocked = get_achievement_stats(STEAM_API_KEY, STEAM_ID, app_id)

        t_label = str(total)    if total    is not None else "—"
        u_label = str(unlocked) if unlocked is not None else "—"
        print(f"{i:<5} {name[:44]:<45} {playtime:>14} {u_label:>9} {t_label:>7}")

        results.append({
            "name":              name,
            "app_id":            app_id,
            "playtime_minutes":  minutes,
            "playtime_display":  playtime,
            "total_achievements":    total,
            "unlocked_achievements": unlocked,
        })

        # Be polite to the API — avoid rate limiting
        time.sleep(0.3)

    # ── Summary ──────────────────────────────────────────────────────────────
    games_with_achv  = [r for r in results if r["total_achievements"] is not None]
    total_achv       = sum(r["total_achievements"]    for r in games_with_achv)
    total_unlocked   = sum(r["unlocked_achievements"] for r in games_with_achv)
    total_minutes    = sum(r["playtime_minutes"]      for r in results)

    print("-" * 84)
    print(f"\nSUMMARY")
    print(f"  Total games in library           : {len(games)}")
    print(f"  Games with achievements          : {len(games_with_achv)}")
    print(f"  Total achievements available     : {total_achv}")
    print(f"  Total achievements unlocked      : {total_unlocked}")
    if total_achv:
        pct = total_unlocked / total_achv * 100
        print(f"  Overall completion               : {pct:.1f}%")
    print(f"  Total playtime                   : {format_playtime(total_minutes)}")

    if games_with_achv:
        top = max(games_with_achv, key=lambda r: r["total_achievements"])
        print(f"  Most achievements in one game    : {top['name']} ({top['total_achievements']})")
        most_played = max(results, key=lambda r: r["playtime_minutes"])
        print(f"  Most played game                 : {most_played['name']} ({most_played['playtime_display']})")

    # ── CSV Export ───────────────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file  = f"steam_achievements_{timestamp}.csv"

    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "#", "Game", "App ID",
            "Playtime (raw minutes)", "Playtime (h/m/s)",
            "Unlocked Achievements", "Total Achievements",
        ])
        for i, r in enumerate(results, 1):
            writer.writerow([
                i,
                r["name"],
                r["app_id"],
                r["playtime_minutes"],
                r["playtime_display"],
                r["unlocked_achievements"] if r["unlocked_achievements"] is not None else "",
                r["total_achievements"]    if r["total_achievements"]    is not None else "",
            ])

        # Blank row then summary
        writer.writerow([])
        writer.writerow(["SUMMARY", "", "", "", "", "", ""])
        writer.writerow(["Total games in library",       "", "", "", "", "", len(games)])
        writer.writerow(["Games with achievements",      "", "", "", "", "", len(games_with_achv)])
        writer.writerow(["Total achievements available", "", "", "", "", "", total_achv])
        writer.writerow(["Total achievements unlocked",  "", "", "", "", "", total_unlocked])
        if total_achv:
            writer.writerow(["Overall completion (%)",  "", "", "", "", "", f"{pct:.1f}%"])
        writer.writerow(["Total playtime",              "", "", total_minutes, format_playtime(total_minutes), "", ""])
        if games_with_achv:
            writer.writerow(["Most achievements in one game", top["name"],         top["app_id"],         "", "", "", top["total_achievements"]])
            writer.writerow(["Most played game",              most_played["name"], most_played["app_id"], most_played["playtime_minutes"], most_played["playtime_display"], "", ""])

    print(f"\nResults saved to: {csv_file}")


if __name__ == "__main__":
    main()