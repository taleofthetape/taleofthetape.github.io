# Tale of the Tape

A daily UFC fighter guessing game, test your MMA knowledge by identifying a mystery fighter based on their stats!

All the other UFC daily games are kind of shit, so I built my own. Have fun!

## How to Play

- Guess a ranked UFC fighter from the male divisions
- Compare your guess against the mystery fighter's stats:
  - **Green**: Exact match
  - **Amber**: Close value
  - **Red**: Wrong, with arrows indicating if the target is higher ↑ or lower ↓
- You have 10 attempts to identify the correct fighter
- A new fighter is selected daily at 05:00 UTC

## Stats Compared

- Division & Weight Class
- UFC Ranking
- Career Wins
- Strikes Landed per Minute (SLpM)
- Strikes Absorbed per Minute (SApM)
- Takedown Average
- Submission Average
- Total Fight Time

## Play Now

**Live Game**: [taleofthetape.github.io](https://taleofthetape.github.io/)

## Repositories

- **Host Repository**: [github.com/taleofthetape/taleofthetape.github.io](github.com/taleofthetape/taleofthetape.github.io)

## Technical Details

- Frontend: Vanilla HTML/CSS/JavaScript
- Data: Scraped daily from UFC.com via GitHub Actions
- Hosting: GitHub Pages
- Fighter pool: Ranked fighters from male UFC divisions only

---

Built by [Zach Winship](https://github.com/zwinship)
