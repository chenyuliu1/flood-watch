# Maribyrnong Flood Watch Dashboard

A real-time flood monitoring dashboard for authorities (Melbourne Water, MCC, BoM, SES) in the Maribyrnong area. This is our team's prototype for ENGR90051 — it demonstrates how fragmented flood data from multiple agencies can be pulled into one place so decision-makers can act faster.

## What this actually is

Our HMW statement asks: *How might we create an accurate, accessible flood information system that effectively stores and communicates risk data to authorities?*

This dashboard is our answer. It takes data from 6 different sources (which in real life are managed by different agencies that don't share data well) and combines them into one screen:

| Dashboard section | What it shows | Real-world data source |
|---|---|---|
| Water level chart | Live sensor readings | Melbourne Water (sensor) |
| Rainfall numbers | 24h rainfall by area | Bureau of Meteorology |
| Flood risk map | Areas colour-coded by risk | Council / Data Vic (elevation, drainage) |
| Priority list | Which area needs attention first | All sources combined |
| CALD demographics | Vulnerable population stats | ABS Census |
| Risk score | Overall threat level (NORMAL/WARNING/DANGER) | Calculated from all 6 sources |

The key idea: right now these datasets are scattered across MW, MCC, BoM, and SES. Our research (interviews with the Senior Drainage Engineer at MCC and a community rep affected by the 2022 flood) showed that the problem isn't missing data — it's that existing data is fragmented and doesn't get turned into decisions fast enough. MCC's flood model took 2 years to update after the 2022 flood. This dashboard is meant to show what it could look like if that data was integrated and updated in real time.

## How to run it (step by step)

You need: a laptop with Chrome and Python installed.

### 1. Download the project

Download the whole folder to your computer. Put it somewhere easy to find, like your Desktop.

You should have these files in one folder:
```
index.html
app.js
styles.css
flask_api.py
sensor_history.csv
rainfall.csv
flood_zones.csv
population.csv
```

### 2. Open a terminal

- **Mac**: open "Terminal" (search for it in Spotlight)
- **Windows**: open "Command Prompt" or "PowerShell" (search in Start menu)

### 3. Go to the project folder

Type `cd` then the path to your folder. For example:

```
cd Desktop/flood-watch
```

If you're not sure of the path, you can drag the folder into the terminal window and it'll paste the path for you.

### 4. Install Flask (only need to do this once)

```
pip install flask flask-cors
```

If `pip` doesn't work, try `pip3` instead. If neither works, you probably need to install Python first — download it from python.org.

### 5. Start the backend server

```
python flask_api.py
```

(On Mac, you might need `python3 flask_api.py` instead.)

You should see something like:
```
 * Running on http://0.0.0.0:5001
```

Leave this terminal window open. Don't close it — the server needs to keep running.

### 6. Open the dashboard

Open `index.html` in Chrome. Just double-click it, or drag it into a Chrome window.

You should see the dashboard with "NORMAL" status and some data loading in.

### 7. Test it

Click the green **Simulate** button. You'll see the water level chart start drawing a line going up and down — this simulates what the Arduino sensor would send in real life. The risk level and numbers will update as the simulated water rises.

To stop, click the red **Stop** button.

## Demo day setup (May 25)

1. One laptop runs Flask (`python flask_api.py`) — keep the terminal open
2. Open `index.html` in Chrome on the same laptop
3. Plug the Arduino into the laptop via USB
4. Click **Connect Arduino** and pick the serial port from the popup
5. The chart will start showing real sensor data, and the risk level will update live
6. If Arduino isn't available for any reason, click **Simulate** instead — it does the same thing with fake data

If you want to update rainfall data for demo day, open `rainfall.csv` in any text editor and change the dates in the first column to the demo date and the days before it.

## How the risk score works

Each area (Maribyrnong, Footscray, Braybrook, Maidstone, West Footscray) gets a score out of 100 based on 6 factors:

- **Current water level** (20%) — from the Arduino sensor
- **Rainfall** (20%) — from BOM data (rainfall.csv)
- **Flood history** (20%) — how often the area has flooded before (flood_zones.csv)
- **Elevation / water proximity** (15%) — lower areas flood first (flood_zones.csv)
- **Drainage capacity** (15%) — some areas drain worse than others (flood_zones.csv)
- **Community vulnerability** (10%) — CALD percentage, elderly, low English proficiency (population.csv)

If water is rising fast, the score gets a multiplier on top.

Score >= 65 = DANGER, >= 40 = WARNING, otherwise NORMAL.

You can click on any area in the Priority list to see a breakdown of what's driving its risk score, which agency owns that data, and how it compares to other areas.

## Why it looks the way it does

The dashboard is designed for authority users (MW, MCC staff), not the general public. The visual style is intentionally minimal and document-like — it's meant to feel like a professional monitoring tool, not a flashy app. Specifically:

- **Agency labels on each card** (Melbourne Water, BOM, Council, ABS Census) — directly shows where each piece of data comes from. This addresses the fragmentation problem: you can see at a glance that the system is pulling from multiple agencies.
- **Agency tags on flagged issues** (colour-coded by responsible department) — so when something is wrong, you immediately know whose job it is to act on it.
- **Risk score combining all sources** — the single NORMAL/WARNING/DANGER indicator is the whole point. Instead of checking 6 different systems, the operator sees one number.
- **Daily reports with CSV export** — data needs to be stored and accessible over time, not just shown live. This addresses the "loss of knowledge" gap identified in our MCC interview.
- **Real-time chart** — addresses Paul's testimony that warnings arrived too late. The sensor updates every few seconds.

## Files

**Code (4 files):**
- `index.html` — the dashboard page
- `styles.css` — how it looks
- `app.js` — handles the Arduino connection, draws the chart, talks to Flask
- `flask_api.py` — the backend server that stores sensor data and calculates risk

**Data (4 CSV files):**
- `sensor_history.csv` — gets filled automatically when the sensor sends data. Don't edit this by hand.
- `rainfall.csv` — BOM rainfall per area per day. Update dates before demo if needed.
- `flood_zones.csv` — static info about each area (elevation, flood history, drainage). Doesn't change.
- `population.csv` — ABS Census demographics. Doesn't change.

## For the Leaflet map (Adi)

The Flask server has two API endpoints you can fetch from:

**`GET http://localhost:5001/risk_by_area`** — risk data per area, good for colouring map markers:
```json
{
  "areas": [
    {
      "area": "Maribyrnong",
      "lat": -37.7743, "lng": 144.8893,
      "level": "WARNING",
      "overall_score": 57.0,
      "population": 3200,
      "all_factors": { ... }
    }
  ]
}
```
Fields you need for the map: `area`, `lat`, `lng`, `level`, `overall_score`.

**`GET http://localhost:5001/data`** — raw data from all 4 CSVs if you need the actual numbers.

Both update every 10 seconds on the dashboard side, so just poll on a timer.
