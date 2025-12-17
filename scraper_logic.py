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

RANKINGS_URL = "https://www.ufc.com/rankings"
BASE_URL = "https://www.ufc.com"
PRODUCTION_OUTPUT_FILE = "game_data.json"
PAST_DAYS_LIMIT = 7
REQUEST_SLEEP = 1.0

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 TaleOfTheTapeBot",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

XPATH_SLOT_A = (
    "/html/body/div[1]/div/main/div[1]/div/div/div/div/div[4]/div[2]/div/div"
    "/section/ul/li[1]/article/div[1]/div/div/div/div[1]/a/div/img/@src"
)

XPATH_SLOT_B = (
    "/html/body/div[1]/div/main/div[1]/div/div/div/div/div[4]/div[2]/div/div"
    "/section/ul/li[1]/article/div[1]/div/div/div/div[2]/a/div/img/@src"
)


def get_soup(url: str) -> Union[BeautifulSoup, None]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return BeautifulSoup(resp.content, "html.parser")
    except requests.RequestException:
        return None


def time_to_seconds(time_str: str) -> int:
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
    return re.sub(r"[^a-z]", "", text.lower())


def filename_matches_fighter(url: str, fighter_name: str) -> bool:
    if not url:
        return False
    fname = normalize(url.split("/")[-1])
    parts = [normalize(p) for p in fighter_name.split()]
    return all(p in fname for p in parts)


def load_game_data(file_name: str) -> Dict[str, Any]:
    if os.path.exists(file_name):
        try:
            with open(file_name, "r") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    data.setdefault("daily_fighter", {})
                    data.setdefault("past_fighters", [])
                    data.setdefault("fighter_data", {})
                    return data
        except json.JSONDecodeError:
            pass
    return {
        "daily_fighter": {},
        "past_fighters": [],
        "fighter_data": {}
    }


def save_game_data(data: Dict[str, Any], file_name: str) -> None:
    with open(file_name, "w") as f:
        json.dump(data, f, indent=4)


def scrape_rankings() -> List[Dict[str, Any]]:
    soup = get_soup(RANKINGS_URL)
    if soup is None:
        return []

    fighters: List[Dict[str, Any]] = []

    division_blocks = soup.select("div.view-grouping")
    if not division_blocks:
        division_blocks = soup.select("div.c-rankings__content > div.c-rankings__division")

    if not division_blocks:
        return []

    for block in division_blocks:      
        division_name = None

        header = block.select_one("div.view-grouping-header")
        if header and header.get_text(strip=True):
            division_name = header.get_text(strip=True)
        if not division_name:
            cap_h4 = block.select_one("table caption h4")
            if cap_h4 and cap_h4.get_text(strip=True):
                division_name = cap_h4.get_text(strip=True)
            
        if not division_name:
            division_name = "Unknown Division"

        # Skip women's divisions
        if division_name.strip().lower().startswith("women"):
            continue

        table = block.select_one("table")
        if not table:
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

        # Ranked fighters
        rows = table.select("tbody tr")

        for row in rows:
            rank_td = row.select_one("td:nth-of-type(1)")
            name_a = row.select_one("td:nth-of-type(2) a")

            if not rank_td or not name_a:
                continue

            rank_text = rank_td.get_text(strip=True)
            name_text = name_a.get_text(strip=True)
            href = name_a.get("href", "")
            profile_url = BASE_URL + href if href.startswith("/") else href or None

            if not rank_text or (not rank_text[0].isdigit() and rank_text.upper() not in ["P4P", "C"]):
                continue

            fighters.append({
                "Name": name_text,
                "Division": division_name,
                "Rank": rank_text,
                "Profile_URL": profile_url
            })

    return fighters


def scrape_fighter_image(tree: html.HtmlElement, fighter_name: str) -> str:
    slot_a = tree.xpath(XPATH_SLOT_A)
    slot_b = tree.xpath(XPATH_SLOT_B)

    a_url = slot_a[0] if slot_a else None
    b_url = slot_b[0] if slot_b else None

    if filename_matches_fighter(a_url, fighter_name):
        return a_url
    elif filename_matches_fighter(b_url, fighter_name):
        return b_url
    else:
        return a_url if a_url else "N/A"


def scrape_fighter_stats(name: str, profile_url: Union[str, None]) -> Union[Dict[str, Any], None]:
    if not profile_url:
        return None

    try:
        resp = requests.get(profile_url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    try:
        tree = html.fromstring(resp.content)
    except Exception:
        return None

    def xp_text(path: str) -> str:
        try:
            res = tree.xpath(path)
            if not res:
                return "N/A"
            return str(res[0].text_content()).strip()
        except Exception:
            return "N/A"

    picture_url = scrape_fighter_image(tree, name)

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

    final_stats = {k: v for k, v in stats.items() if v not in [None, "", "N/A", "-"]}
    final_stats["Name"] = name
    
    if "Picture_URL" not in final_stats:
        final_stats["Picture_URL"] = picture_url

    return final_stats if len(final_stats) > 2 else None


def scrape_all_ranked_fighters_into_data(game_data: Dict[str, Any]) -> Dict[str, Any]:
    fighters = scrape_rankings()
    if not fighters:
        return game_data

    fighter_index: Dict[str, Dict[str, Any]] = {}
    for f in fighters:
        fighter_index[f["Name"]] = f

    for name, info in list(fighter_index.items()):
        profile_url = info.get("Profile_URL")
        existing = game_data["fighter_data"].get(name)

        should_rescrape = (
            not existing
            or not existing.get("Record")
            or not existing.get("Picture_URL")
            or not filename_matches_fighter(existing.get("Picture_URL"), name)
        )

        if not should_rescrape:
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

        time.sleep(REQUEST_SLEEP)

    return game_data


def select_daily_fighter(game_data: Dict[str, Any]) -> None:
    all_fighters = game_data.get("fighter_data", {})
    if not all_fighters:
        return

    past = set(game_data.get("past_fighters", []))

    available = [
        name for name, data in all_fighters.items()
        if name not in past and data.get("Record")
    ]

    # Reset history if all fighters have been used
    if not available and all_fighters:
        game_data["past_fighters"] = []
        past = set()
        available = [
            name for name, data in all_fighters.items()
            if data.get("Record")
        ]

    if not available:
        return

    chosen_name = random.choice(available)
    chosen_data = all_fighters[chosen_name]

    prev_name = game_data.get("daily_fighter", {}).get("Name")
    if prev_name and prev_name not in past:
        game_data["past_fighters"].append(prev_name)

    game_data["past_fighters"] = game_data["past_fighters"][-PAST_DAYS_LIMIT:]

    chosen_data["Selected_Date"] = datetime.utcnow().isoformat() + "Z"
    game_data["daily_fighter"] = chosen_data


def main() -> None:
    output_file = PRODUCTION_OUTPUT_FILE

    game_data = load_game_data(output_file)
    game_data = scrape_all_ranked_fighters_into_data(game_data)
    select_daily_fighter(game_data)
    save_game_data(game_data, output_file)


if __name__ == "__main__":
    main()
