# Save this content as 'scraper_logic.py'

import requests
from bs4 import BeautifulSoup
import json
import random
import os
import time
import re
from datetime import datetime
from lxml import html
from typing import List, Dict, Union, Any

# ------------------ CONFIG ------------------ #

RANKINGS_URL = "https://www.ufc.com/rankings"
BASE_URL = "https://www.ufc.com"

# --- PRODUCTION OUTPUT FILE ---
PRODUCTION_OUTPUT_FILE = "game_data.json"

PAST_DAYS_LIMIT = 7
REQUEST_SLEEP = 1.0

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 TaleOfTheTapeBot",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# --- IMAGE XPATHS (SLOT A AND SLOT B) ---
XPATH_SLOT_A = (
    "/html/body/div[1]/div/main/div[1]/div/div/div/div/div[4]/div[2]/div/div"
    "/section/ul/li[1]/article/div[1]/div/div/div/div[1]/a/div/img/@src"
)

XPATH_SLOT_B = (
    "/html/body/div[1]/div/main/div[1]/div/div/div/div/div[4]/div[2]/div/div"
    "/section/ul/li[1]/article/div[1]/div/div/div/div[2]/a/div/img/@src"
)

# ------------------ UTILITIES ------------------ #

def get_soup(url: str) -> Union[BeautifulSoup, None]:
    """Fetch a URL and return BeautifulSoup object, or None on error."""
    try:
        print(f"  [HTTP] GET {url}")
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
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


def normalize(text: str) -> str:
    """Normalize text by removing all non-alphabetic characters and converting to lowercase."""
    return re.sub(r"[^a-z]", "", text.lower())


def filename_matches_fighter(url: str, fighter_name: str) -> bool:
    """Check if the image URL filename matches the fighter's name."""
    if not url:
        return False

    # Extract filename from URL and normalize it
    fname = normalize(url.split("/")[-1])
    
    # Normalize each part of the fighter's name
    parts = [normalize(p) for p in fighter_name.split()]

    # All name parts should be present in the filename
    return all(p in fname for p in parts)


def load_game_data(file_name: str) -> Dict[str, Any]:
    """Load saved data from JSON file, or return new structure."""
    if os.path.exists(file_name):
        try:
            with open(file_name, "r") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    print(f"Loaded existing data from {file_name}")
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

    # Use primary and fallback selectors for division blocks
    division_blocks = soup.select("div.view-grouping")
    if not division_blocks:
        division_blocks = soup.select("div.c-rankings__content > div.c-rankings__division")

    if not division_blocks:
        print("!!! CRITICAL: Could not find any division blocks on rankings page.")
        return []

    for block in division_blocks:      
        division_name = None

        # Determine division name
        header = block.select_one("div.view-grouping-header")
        if header and header.get_text(strip=True):
            division_name = header.get_text(strip=True)
        if not division_name:
            cap_h4 = block.select_one("table caption h4")
            if cap_h4 and cap_h4.get_text(strip=True):
                division_name = cap_h4.get_text(strip=True)
            
        if not division_name:
            division_name = "Unknown Division"

        print(f"  -- Processing Division: {division_name} --")

        # 🔥 SKIP WOMEN'S DIVISIONS
        if division_name.strip().lower().startswith("women"):
            print(f"    Skipping women's division: {division_name}")
            continue

        table = block.select_one("table")
        if not table:
            print("    !! No <table> found in this division block.")
            continue

        # Champion
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

        # Ranked fighters
        rows = table.select("tbody tr")
        found_in_division = 0

        for row in rows:
            rank_td = row.select_one("td:nth-of-type(1)")
            name_a = row.select_one("td:nth-of-type(2) a")

            if not rank_td or not name_a:
                continue

            rank_text = rank_td.get_text(strip=True)
            name_text = name_a.get_text(strip=True)
            href = name_a.get("href", "")
            profile_url = BASE_URL + href if href.startswith("/") else href or None

            # Only accept real numeric ranks (or P4P)
            if not rank_text or (not rank_text[0].isdigit() and rank_text.upper() not in ["P4P", "C"]):
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


# ------------------ FIGHTER STATS SCRAPER (WITH FIXED IMAGE LOGIC) ------------------ #

def scrape_fighter_image(tree: html.HtmlElement, fighter_name: str) -> str:
    """
    Extract fighter image using Slot A/B logic with filename matching.
    Returns the best matching image URL or "N/A".
    """
    # Try to extract both slot URLs
    slot_a = tree.xpath(XPATH_SLOT_A)
    slot_b = tree.xpath(XPATH_SLOT_B)

    a_url = slot_a[0] if slot_a else None
    b_url = slot_b[0] if slot_b else None

    print(f"  Image Slot A: {a_url}")
    print(f"  Image Slot B: {b_url}")

    # Check which slot matches the fighter's name
    if filename_matches_fighter(a_url, fighter_name):
        print(f"  ✅ Image match found in Slot A")
        return a_url
    elif filename_matches_fighter(b_url, fighter_name):
        print(f"  ✅ Image match found in Slot B")
        return b_url
    else:
        # Fallback to Slot A if no match found
        print(f"  ⚠️ No filename match — falling back to Slot A")
        return a_url if a_url else "N/A"


def scrape_fighter_stats(name: str, profile_url: Union[str, None]) -> Union[Dict[str, Any], None]:
    """
    Scrape stats for a fighter using lxml and XPaths.
    """
    if not profile_url:
        print(f"!!! No profile URL for {name}, skipping stats scrape.")
        return None

    print(f"\n--- Scraping Stats for {name} ---")
    try:
        print(f"  [HTTP] GET {profile_url}")
        resp = requests.get(profile_url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"!!! HTTP error fetching {profile_url} for {name}: {e}")
        return None

    try:
        # Parse content using lxml's parser
        tree = html.fromstring(resp.content)
    except Exception as e:
        print(f"!!! Error parsing HTML for {name}: {e}")
        return None

    def xp_text(path: str) -> str:
        """Helper to safely extract text content using XPath."""
        try:
            res = tree.xpath(path)
            if not res:
                return "N/A"
            return str(res[0].text_content()).strip()
        except Exception:
            return "N/A"

    # --- Extract Image Using Fixed Logic ---
    picture_url = scrape_fighter_image(tree, name)

    # --- XPaths for Other Stats ---
    stats = {
        "Name": name,
        "Profile_URL": profile_url,
        "Picture_URL": picture_url,
        "Record": xp_text(
            '/html/body/div[1]/div/main/div[1]/div/div/div/div/div[1]/div/div/div[1]/div[2]/p[2]'
        ),
        "SLpM": xp_text(
            '/html/body/div[1]/div/main/div[1]/div/div/div/div/div[3]/div/div/div[2]/div[4]/div/div[1]/div[1]/div[1]'
        ),
        "SApM": xp_text(
            '/html/body/div[1]/div/main/div[1]/div/div/div/div/div[3]/div/div/div[2]/div[4]/div/div[1]/div[2]/div[1]'
        ),
        "TD_Avg": xp_text(
            '/html/body/div[1]/div/main/div[1]/div/div/div/div/div[3]/div/div/div[2]/div[4]/div/div[2]/div[1]/div[1]'
        ),
        "Sub_Avg": xp_text(
            '/html/body/div[1]/div/main/div[1]/div/div/div/div/div[3]/div/div/div[2]/div[4]/div/div[2]/div[2]/div[1]'
        ),
        "Fight_Time": xp_text(
            '/html/body/div[1]/div/main/div[1]/div/div/div/div/div[3]/div/div/div[2]/div[5]/div/div[3]/div[2]/div[1]'
        ),
    }
    
    stats["Fight_Time_Seconds"] = time_to_seconds(stats["Fight_Time"])

    # Filter out totally empty / useless results
    final_stats = {k: v for k, v in stats.items() if v not in [None, "", "N/A", "-"]}
    final_stats["Name"] = name  # Ensure name is present
    
    # Keep Picture_URL even if it's "N/A" for debugging purposes
    if "Picture_URL" not in final_stats:
        final_stats["Picture_URL"] = picture_url

    print(f"  > Final Stats Extracted: {len(final_stats)} keys.")
    return final_stats if len(final_stats) > 2 else None


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
    
    # Use list() for consistent iteration 
    for i, (name, info) in enumerate(list(fighter_index.items()), start=1):
        print(f"\n[{i}/{len(fighter_index)}] {name}")

        profile_url = info.get("Profile_URL")
        existing = game_data["fighter_data"].get(name)

        # Rescrape if we don't have the fighter OR if their record is missing/empty
        should_rescrape = (
            not existing
            or not existing.get("Record")
            or not existing.get("Picture_URL")
            or not filename_matches_fighter(existing.get("Picture_URL"), name)
        )

        if not should_rescrape:
            print("  Skipping (already have stats with Record).")
            # Update Division/Rank/URL in case they moved
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

        # Pause between individual fighter requests
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
