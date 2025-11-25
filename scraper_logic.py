import requests
from bs4 import BeautifulSoup
import json
import random
import os
from datetime import datetime

# --- Configuration ---
RANKINGS_URL = "https://www.ufc.com/rankings"
BASE_ATHLETE_URL = "https://www.ufc.com/athlete/"
DATA_FILE = "game_data.json"
PAST_DAYS_LIMIT = 7

# --- Helper Functions ---
def sanitize_fighter_name(name):
    """Converts 'First Last' to 'first-last' for URL slug."""
    # Handle names like 'Jiri Prochazka' -> 'jiri-prochazka'
    return name.lower().replace('.', '').replace(' ', '-').replace("'", "")

def load_game_data():
    """Loads existing game data or creates a new structure."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {
        "daily_fighter": {},
        "past_fighters": [], # List of fighter names to avoid
        "fighter_data": {}   # All scraped fighter stats
    }

def save_game_data(data):
    """Saves updated game data."""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def scrape_fighter_stats(fighter_name):
    """Scrapes individual fighter stats from their athlete page."""
    slug = sanitize_fighter_name(fighter_name)
    url = f"{BASE_ATHLETE_URL}{slug}"
    print(f"Scraping stats for: {fighter_name} from {url}")

    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
    except requests.RequestException as e:
        print(f"Error fetching stats for {fighter_name}: {e}")
        return None

    # NOTE: The provided XPaths are extremely brittle. I will use more robust
    # selectors where possible, but still based on your structure.
    
    # Function to safely get text content from an XPath
    def safe_extract(xpath):
        # NOTE: Using lxml's XPath engine for a slight performance boost and accuracy
        # This requires the lxml dependency installed.
        element = soup.find(xpath=xpath)
        return element.text.strip() if element else "N/A"

    # Scraping the stats using the provided XPaths (or similar):
    stats = {
        "Name": fighter_name,
        # Record: /html/body/div[1]/div/main/div[1]/div/div/div/div/div[1]/div/div/div[1]/div[2]/p[2]
        "Record": safe_extract('/html/body/div[1]/div/main/div[1]/div/div/div/div/div[1]/div/div/div[1]/div[2]/p[2]'),
        
        # Fighter Picture URL (Using a more generic search for the image source)
        "Picture_URL": soup.find('img', class_='e-person--image')['src'] if soup.find('img', class_='e-person--image') else 'N/A',

        # Sig. Strikes Landed / Min
        "SLpM": safe_extract('div.c-stat-body:nth-child(4) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1)'),
        
        # Sig. Strikes Absorbed / Min
        "SApM": safe_extract('div.c-stat-body:nth-child(4) > div:nth-child(1) > div:nth-child(2) > div:nth-child(1)'),

        # Takedown Avg / 15 Min
        "TD_Avg": safe_extract('div.c-stat-body:nth-child(4) > div:nth-child(2) > div:nth-child(1) > div:nth-child(1)'),

        # Submission Avg / 15 Min
        "Sub_Avg": safe_extract('div.c-stat-body:nth-child(4) > div:nth-child(2) > div:nth-child(2) > div:nth-child(1)'),
        
        # Average Fight Time (This XPath is usually very unstable)
        "Fight_Time": safe_extract('div.c-stat-body:nth-child(5) > div:nth-child(3) > div:nth-child(2) > div:nth-child(1)')
    }

    # Add other common guessable stats (usually found in the main info box)
    fighter_info_box = soup.find('div', class_='c-bio__info-details')
    if fighter_info_box:
        # These fields are usually listed as key/value pairs
        # Find 'STANCE' label and get the value
        stance_label = fighter_info_box.find('p', text='STANCE')
        stats['Stance'] = stance_label.find_next_sibling('p').text.strip() if stance_label and stance_label.find_next_sibling('p') else 'N/A'

        # Find 'HEIGHT' label and get the value
        height_label = fighter_info_box.find('p', text='HEIGHT')
        stats['Height'] = height_label.find_next_sibling('p').text.strip() if height_label and height_label.find_next_sibling('p') else 'N/A'
        
        # Find 'WEIGHT' label and get the value
        weight_label = fighter_info_box.find('p', text='WEIGHT')
        stats['Weight'] = weight_label.find_next_sibling('p').text.strip() if weight_label and weight_label.find_next_sibling('p') else 'N/A'

    # Filter out empty or 'N/A' stats that won't be useful for the game
    return {k: v for k, v in stats.items() if v and v != 'N/A' and v != '-'}


def scrape_all_ranked_fighters():
    """Scrapes all ranked fighters (Champion + Ranks 1-15) across all divisions."""
    print("Starting master scrape of UFC Rankings...")
    fighters = []

    try:
        response = requests.get(RANKINGS_URL, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
    except requests.RequestException as e:
        print(f"Error fetching rankings: {e}")
        return fighters

    # Locate the main container for all divisions (c-rankings__content)
    # The structure uses multiple nested divs (div[n]) which is why the XPaths are long.
    # We will try to loop through the division blocks.
    division_blocks = soup.select('div.c-rankings__content > div.c-rankings__division')

    for block in division_blocks:
        # Get Division Name (e.g., Flyweight)
        division_name_tag = block.select_one('h4.c-rankings-title__text')
        division = division_name_tag.text.strip() if division_name_tag else 'Unknown Division'
        
        print(f"  -- Processing {division} --")

        # 1. Scrape Champion
        champion_tag = block.select_one('div.c-rankings-title__champion a')
        if champion_tag:
            champion_name = champion_tag.text.strip()
            fighters.append({
                "Name": champion_name,
                "Division": division,
                "Rank": "C"
            })
        
        # 2. Scrape Ranked Fighters (Ranks 1-15)
        # Table body contains the rows for ranked fighters
        ranked_rows = block.select('table.b-list__table-box__body tr')
        for row in ranked_rows:
            rank_tag = row.select_one('td.b-list__table-box-head_rank > span')
            name_tag = row.select_one('td.b-list__table-box__td > a')
            
            if rank_tag and name_tag:
                rank = rank_tag.text.strip()
                name = name_tag.text.strip()
                # Exclude the champion if they are accidentally listed as #1
                if rank.isdigit() and int(rank) >= 1:
                     fighters.append({
                        "Name": name,
                        "Division": division,
                        "Rank": rank
                    })

    return fighters

def main():
    game_data = load_game_data()
    all_fighters = scrape_all_ranked_fighters()
    
    # 1. Scrape All Detailed Stats and Store
    for fighter in all_fighters:
        name = fighter['Name']
        # Only scrape if we haven't already scraped their full stats today
        if name not in game_data["fighter_data"] or not game_data["fighter_data"][name]:
            stats = scrape_fighter_stats(name)
            if stats:
                # Merge ranking/division data with scraped stats
                stats.update({"Division": fighter["Division"], "Rank": fighter["Rank"]})
                game_data["fighter_data"][name] = stats
            else:
                # If scraping failed, remove the fighter from the pool
                print(f"Could not get stats for {name}. Removing from pool.")
                continue
        # Ensure the division/rank info is up-to-date even if stats weren't re-scraped
        else:
             game_data["fighter_data"][name].update({"Division": fighter["Division"], "Rank": fighter["Rank"]})


    # 2. Pick a New Daily Fighter
    available_fighters = [
        name for name in game_data["fighter_data"].keys()
        if name not in game_data["past_fighters"]
    ]
    
    if available_fighters:
        # Randomly select a new fighter from the available pool
        daily_fighter_name = random.choice(available_fighters)
        daily_fighter_data = game_data["fighter_data"][daily_fighter_name]
        
        # Set the new daily fighter
        game_data["daily_fighter"] = daily_fighter_data
        
        # 3. Update Past Fighters List
        # Add the *previous* daily fighter to the past_fighters list
        previous_fighter_name = game_data["daily_fighter"].get("Name")
        if previous_fighter_name and previous_fighter_name not in game_data["past_fighters"]:
             game_data["past_fighters"].append(previous_fighter_name)

        # Truncate the list to the last 7 unique fighters
        game_data["past_fighters"] = game_data["past_fighters"][-PAST_DAYS_LIMIT:]
        
        print(f"\n--- Success! New Daily Fighter is: {daily_fighter_name} ---")
        
    else:
        print("\n!!! Warning: No unique fighters available. Resetting past fighters list. !!!")
        game_data["past_fighters"] = []
        # Try to pick again (or just let the old one stand, but logging the issue)
        # For simplicity, we will just log the issue and keep the old one or break.

    # 4. Save Final Data
    save_game_data(game_data)
    print(f"\nSaved updated game data to {DATA_FILE}")

if __name__ == "__main__":
    main()
