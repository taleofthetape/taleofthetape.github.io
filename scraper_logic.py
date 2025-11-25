# Save this content as 'scraper_logic.py'

import requests
from bs4 import BeautifulSoup
import json
import random
import os
import time
from datetime import datetime
from typing import List, Dict, Union, Any # Added for clarity

# ------------------ CONFIG ------------------ #

RANKINGS_URL = "https://www.ufc.com/rankings"
BASE_URL = "https://www.ufc.com"

# --- PRODUCTION OUTPUT FILE ---
PRODUCTION_OUTPUT_FILE = "game_data.json"

PAST_DAYS_LIMIT = 7
REQUEST_SLEEP = 1.0  # Increased sleep slightly for safer server interactions
# Headers mimicking a legitimate browser/scraper
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 TaleOfTheTapeBot",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# ------------------ UTILITIES ------------------ #

def get_soup(url: str) -> Union[BeautifulSoup, None]:
    """Fetch a URL and return BeautifulSoup object, or None on error."""
    try:
        print(f" [HTTP] GET {url}")
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        # Add a slight pause here to prevent rapid sequence of requests
        time.sleep(0.5) 
        return BeautifulSoup(resp.content, "html.parser")
    except requests.RequestException as e:
        print(f"!!! HTTP ERROR for {url}: {e}")
        return None


def time_to_seconds(time_str: str) -> int:
    """Convert 'MM:SS' time string to total seconds (0 if invalid)."""
    if not time_str or time_str.strip() in ["N/A", "-", ""]:
        return 0
    parts = time_str.strip().split(":")
    if len(parts) != 2:
        return 0
    try:
        minutes = int(parts[0])
        seconds = int(parts[1])
        return minutes * 60 + seconds
    except ValueError:
        return 0


def load_game_data(file_name: str) -> Dict[str, Any]:
    """Load saved data from JSON file, or return new structure."""
    if os.path.exists(file_name):
        try:
            with open(file_name, "r") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    print(f"Loaded existing data from {file_name}")
                    # Ensure all keys exist
                    data.setdefault("daily_fighter", {})
                    data.setdefault("past_fighters", [])
                    data.setdefault("fighter_data", {})
                    return data
        except json.JSONDecodeError:
            print(f"!!! WARNING: Could not decode {file_name}. Starting fresh.")
    return {
        "daily_fighter": {},
        "past_fighters": [],
        "fighter_data": {}
    }


def save_game_data(data: Dict[str, Any], file_name: str) -> None:
    """Save data structure to JSON."""
    with open(file_name, "w") as f:
        json.dump(data, f, indent=4)
    print(f"Saved data to {file_name}")


# ------------------ RANKINGS SCRAPER ------------------ #

def scrape_rankings() -> List[Dict[str, Any]]:
    """
    Scrape UFC rankings page and return a list of fighters.
    """

    print("\n==============================================")
    print("Starting master scrape of UFC Rankings...")
    print("==============================================")

    soup = get_soup(RANKINGS_URL)
    if soup is None:
        print("!!! CRITICAL: Could not fetch rankings page.")
        return []

    fighters: List[Dict[str, Any]] = []

    # Use the more current selector first, then fall back to the older one
    division_blocks = soup.select("div.view-grouping")
    if not division_blocks:
        division_blocks = soup.select("div.c-rankings__content > div.c-rankings__division")

    if not division_blocks:
        print("!!! CRITICAL: Could not find any division blocks on rankings page.")
        return []

    for block in division_blocks:      
        division_name = None

        # Try current selector for header
        header = block.select_one("div.view-grouping-header")
        if header and header.get_text(strip=True):
            division_name = header.get_text(strip=True)

        # Try fallback selector for header (for the c-rankings__division blocks)
        if not division_name:
            cap_h4 = block.select_one("table caption h4")
            if cap_h4 and cap_h4.get_text(strip=True):
                division_name = cap_h4.get_text(strip=True)
            
        if not division_name:
            division_name = "Unknown Division"

        print(f"  -- Processing Division: {division_name} --")

        # 🔥 SKIP WOMEN'S DIVISIONS for the men's game
        if division_name.strip().lower().startswith("women"):
            print(f"    Skipping women's division: {division_name}")
            continue

        table = block.select_one("table")
        if not table:
            print("    !! No <table> found in this division block.")
            continue

        # -------------------------
        # Champion (from caption h5 a)
        # -------------------------
        champ_anchor = table.select_one("caption h5 a")
        if champ_anchor:
            champ_name = champ_anchor.get_text(strip=True)
            champ_href = champ_anchor.get("href", "")
            champ_url = BASE_URL + champ_href if champ_href.startswith("/") else champ_href or None

            fighters.append({
                "Name": champ_name,
                "Division": division_name,
                "Rank": "C",
                "Profile_URL": champ_url
            })
            print(f"    > Champion: {champ_name}")

        # -------------------------
        # Ranked fighters (tbody rows)
        # -------------------------
        rows = table.select("tbody tr")
        found_in_division = 0

        for row in rows:
            # Rank: td[1]
            rank_td = row.select_one("td:nth-of-type(1)")
            # Name: td[2] a
            name_a = row.select_one("td:nth-of-type(2) a")

            if not rank_td or not name_a:
                continue

            rank_text = rank_td.get_text(strip=True)
            name_text = name_a.get_text(strip=True)
            href = name_a.get("href", "")
            profile_url = BASE_URL + href if href.startswith("/") else href or None

            # Only accept real numeric ranks (or "P4P")
            if not rank_text or (not rank_text[0].isdigit() and rank_text.upper() != "P4P"):
                continue

            fighters.append({
                "Name": name_text,
                "Division": division_name,
                "Rank": rank_text,
                "Profile_URL": profile_url
            })
            found_in_division += 1

        print(f"    -> Found {found_in_division} ranked fighters in this division.\n")

    unique_names = set(f["Name"] for f in fighters)
    print(f"Total unique fighters found in rankings: {len(unique_names)}")

    return fighters

# ------------------ FIGHTER STATS SCRAPER ------------------ #

def scrape_fighter_stats(name: str, profile_url: Union[str, None]) -> Union[Dict[str, Any], None]:
    """
    Scrape stats for a fighter.
    """

    if not profile_url:
        print(f"!!! No profile URL for {name}, skipping stats scrape.")
        return None

    print(f"\n--- Scraping Stats for {name} ---")
    soup = get_soup(profile_url)
    if soup is None:
        print(f"!!! Error fetching stats page for {name}")
        return None

    # Helpers
    def safe_select_text(sel_list: List[str]) -> str:
        for sel in sel_list:
            el = soup.select_one(sel)
            if el and el.get_text(strip=True):
                return el.get_text(strip=True)
        return "N/A"

    def find_avg_fight_time() -> str:
        li_candidates = soup.select("li.c-overlap__list-item, li.c-view-details__item")
        for li in li_candidates:
            text = li.get_text(" ", strip=True)
            if "Avg. Fight Time" in text:
                val = li.select_one("span.c-overlap__number, span.c-view-details__value")
                if val and val.get_text(strip=True):
                    return val.get_text(strip=True)
        return "N/A"
    
    # Helper for image URL
    def find_image_url() -> str:
        img = soup.select_one("img.e-person--image, img.c-hero__image, img[typeof~='foaf:Image']")
        return img.get("src") if img and img.get("src") else "N/A"


    # Core stats 
    stats = {
        "Name": name,
        "Profile_URL": profile_url,

        "Record": safe_select_text([
            "div.c-bio__row--record p.c-bio__text",
            "span.c-hero__headline-suffix",
            "p.c-bio__text"
        ]),

        "Picture_URL": find_image_url(),

        "SLpM": safe_select_text([
            "div[data-stat='slpm'] div.c-overlap__stats-value",
            "div.c-stat-compare__group:nth-of-type(1) dd"
        ]),
        "SApM": safe_select_text([
            "div[data-stat='sapm'] div.c-overlap__stats-value",
            "div.c-stat-compare__group:nth-of-type(2) dd"
        ]),
        "TD_Avg": safe_select_text([
            "div[data-stat='td-avg'] div.c-overlap__stats-value",
            "div.c-stat-compare__group:nth-of-type(3) dd"
        ]),
        "Sub_Avg": safe_select_text([
            "div[data-stat='sub-avg'] div.c-overlap__stats-value",
            "div.c-stat-compare__group:nth-of-type(4) dd"
        ]),
    }

    stats["Fight_Time"] = find_avg_fight_time()
    stats["Fight_Time_Seconds"] = time_to_seconds(stats["Fight_Time"])

    # Filter out completely empty stats before saving
    final_stats = {k: v for k, v in stats.items() if v not in [None, "", "N/A", "-"]}
    final_stats["Name"] = name # Ensure name is always included even if others fail

    print(f"  > Stats Extracted: {len(final_stats)} keys.")
    return final_stats if len(final_stats) > 1 else None


# ------------------ GAME LOGIC ------------------ #

def scrape_all_ranked_fighters_into_data(game_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Scrape all ranked fighters, then scrape their stats and
    populate game_data["fighter_data"].
    """

    fighters = scrape_rankings()
    if not fighters:
        print("\n!!! No fighters scraped from rankings. Skipping stats scraping.")
        return game_data

    # Map fighters by name (last one wins if duplicates)
    fighter_index: Dict[str, Dict[str, Any]] = {}
    for f in fighters:
        fighter_index[f["Name"]] = f

    print("\n--- Starting detailed fighter stats scraping ---")
    
    # Use list() for consistent iteration while allowing iteration
    for i, (name, info) in enumerate(list(fighter_index.items()), start=1):
        print(f"\n[{i}/{len(fighter_index)}] {name}")

        profile_url = info.get("Profile_URL")
        existing = game_data["fighter_data"].get(name)

        # Rescrape if we don't have the fighter OR if their record is missing/empty
        should_rescrape = not existing or not existing.get("Record")

        if not should_rescrape:
            print("  Skipping (already have stats with Record).")
            # Ensure Division/Rank are updated in case they moved
            game_data["fighter_data"][name].update({
                "Division": info.get("Division"),
                "Rank": info.get("Rank"),
                "Profile_URL": profile_url
            })
            continue

        stats = scrape_fighter_stats(name, profile_url)
        if stats:
            stats.update({
                "Division": info.get("Division"),
                "Rank": info.get("Rank")
            })
            game_data["fighter_data"][name] = stats
        else:
            print(f"!!! Failed to scrape stats for {name}, leaving old/empty data.")

        # Pause between individual fighter requests to be polite
        time.sleep(REQUEST_SLEEP)

    print("\n--- Detailed scraping complete ---")
    return game_data


def select_daily_fighter(game_data: Dict[str, Any]) -> None:
    """Select a new daily fighter, respecting past_fighters and requiring a Record."""

    all_fighters = game_data.get("fighter_data", {})
    if not all_fighters:
        print("\n!!! CRITICAL: No fighter_data available to pick a daily fighter.")
        return

    past = set(game_data.get("past_fighters", []))

    # A fighter is available if they have a Record and aren't in the past list
    available = [
        name for name, data in all_fighters.items()
        if name not in past and data.get("Record")
    ]

    # If all eligible fighters have been used, reset history
    if not available and all_fighters:
        print("\n!!! Warning: All fighters used recently. Resetting past_fighters.")
        game_data["past_fighters"] = []
        past = set()
        available = [
            name for name, data in all_fighters.items()
            if data.get("Record")
        ]

    if not available:
        print("\n!!! CRITICAL: Failed to select a daily fighter. No suitable data available.")
        return

    chosen_name = random.choice(available)
    chosen_data = all_fighters[chosen_name]

    # Add previous daily fighter to past list (before overwriting daily_fighter)
    prev_name = game_data.get("daily_fighter", {}).get("Name")
    if prev_name and prev_name not in past:
        game_data["past_fighters"].append(prev_name)

    # Truncate to last N days
    game_data["past_fighters"] = game_data["past_fighters"][-PAST_DAYS_LIMIT:]

    # Update daily_fighter with current date stamp and the chosen data
    chosen_data["Selected_Date"] = datetime.utcnow().isoformat() + "Z"
    game_data["daily_fighter"] = chosen_data

    print(f"\n--- Success! New Daily Fighter Selected: {chosen_name} ---")
    print(f"--- Past Fighters ({len(game_data['past_fighters'])} total): {game_data['past_fighters']}")


# ------------------ MAIN ENTRYPOINT FOR GITHUB ACTION ------------------ #

def main() -> None:
    """Main function called by the GitHub Action."""
    output_file = PRODUCTION_OUTPUT_FILE
    print(f"Starting production scraper for GitHub Action. Output file: {output_file}\n")

    # 1. Load existing data
    game_data = load_game_data(output_file)

    # 2. Scrape rankings and stats
    game_data = scrape_all_ranked_fighters_into_data(game_data)

    # 3. Select the daily fighter
    select_daily_fighter(game_data)

    # 4. Save data to the file that GitHub Pages will serve
    save_game_data(game_data, output_file)

    print("\n--- SCRAPE COMPLETE ---")
    print("-------------------------------------------------")


if __name__ == "__main__":
    main()
