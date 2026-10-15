// Andrew's Acquaintances — weekly scores, 2026 season
// Guillotine format: the lowest score each week is eliminated.
// To add a week: push a score onto every still-alive team's array (or null
// for teams already out) and add the week number to WEEKS.

const LEAGUE_DATA = {
  generated: "2026-10-14",
  weeks: [1, 2, 3, 4, 5],
  eliminated: {"10": 1, "17": 2, "12": 3, "14": 4, "2": 5},
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
    "1":  [95.73, 82.70, 88.03, 102.21, 151.63],
    "2":  [78.40, 89.60, 117.41, 118.22, 64.95],
    "3":  [91.76, 86.13, 108.84, 102.15, 123.39],
    "4":  [86.34, 92.48, 102.26, 139.98, 90.79],
    "5":  [88.56, 86.72, 92.06, 81.42, 91.95],
    "6":  [69.66, 85.23, 79.53, 133.62, 83.25],
    "7":  [74.82, 91.18, 93.30, 78.54, 133.69],
    "8":  [98.86, 48.89, 63.67, 152.28, 84.21],
    "9":  [83.34, 128.88, 111.94, 121.18, 123.86],
    "10": [60.21, null, null, null, null],
    "11": [67.80, 66.28, 80.03, 92.32, 127.41],
    "12": [102.72, 92.62, 60.16, null, null],
    "13": [73.84, 68.10, 78.35, 119.64, 74.97],
    "14": [88.84, 82.13, 108.84, 72.06, null],
    "15": [89.87, 95.61, 79.33, 78.77, 91.95],
    "16": [97.90, 64.81, 71.28, 124.73, 81.39],
    "17": [62.01, 46.47, null, null, null],
    "18": [83.30, 122.26, 109.39, 81.10, 86.84],
    "19": [81.56, 107.30, 104.19, 73.48, 103.50]
  }
};
