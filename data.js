// Andrew's Acquaintances — weekly scores, 2026 season
// Guillotine format: the lowest score each week is eliminated.
// To add a week: push a score onto every still-alive team's array (or null
// for teams already out) and add the week number to WEEKS.

const LEAGUE_DATA = {
  generated: "2026-09-23",
  weeks: [1, 2],
  eliminated: {"10": 1, "17": 2},
  teams: {
    "1":  "Culpepper's Love Boat",
    "2":  "Jaxson Dart's ReachAround",
    "3":  "Ray Rice's elevator pitch",
    "4":  "Tom Brady's Ladies",
    "5":  "Jeff Garcia's Door Step",
    "6":  "Ladanians cousin",
    "7":  "McNabb's Camp Crush",
    "8":  "Baker's Wife's Husband",
    "9":  "John Elway's Caddy",
    "10": "Qadry Ismail's Womb",
    "11": "Aqib Talib's Starboard",
    "12": "lane's johnson's fluffer",
    "13": "Naber's Brown Goat",
    "14": "ChrisSnee's Father-in-law",
    "15": "Russini's Side Piece",
    "16": "Frank Gore's Spike Coach",
    "17": "Max's team",
    "18": "TB12's Never Around",
    "19": "George Pickens' Worms"
  },
  points: {
    "1":  [95.73, 82.70],
    "2":  [78.40, 89.60],
    "3":  [91.76, 86.13],
    "4":  [86.34, 92.48],
    "5":  [88.56, 86.72],
    "6":  [69.66, 85.23],
    "7":  [74.82, 91.18],
    "8":  [98.86, 48.89],
    "9":  [83.34, 128.88],
    "10": [60.21, null],
    "11": [67.80, 66.28],
    "12": [102.72, 92.62],
    "13": [73.84, 68.10],
    "14": [88.84, 82.13],
    "15": [89.87, 95.61],
    "16": [97.90, 64.81],
    "17": [62.01, 46.47],
    "18": [83.30, 122.26],
    "19": [81.56, 107.30]
  }
};
