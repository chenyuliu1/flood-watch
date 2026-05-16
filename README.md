# Flood Watch Dashboard

## How to run

```
pip install flask flask-cors
python3 flask_api.py          # Mac/Linux
python flask_api.py           # Windows
```

Then open `index.html` in Chrome. Click "Simulate" to test with fake data, or "Connect Arduino" to use the Arduino sensor. Flask needs to be running or the dashboard won't load data.

On demo day: plug Arduino into one laptop, run Flask, open Chrome.

## Files

**Code:**
- `index.html` - dashboard page
- `app.js` - reads Arduino data through browser, sends to Flask, draws chart
- `styles.css` - styling
- `flask_api.py` - backend, stores sensor data, calculates risk levels from 6 data sources

**Data (CSV):**
- `sensor_history.csv` - auto-generated when Flask receives sensor data. Columns: timestamp, water_level, rate_m_min, raw_distance, arduino_state, yellow_led, red_led, buzzer
- `rainfall.csv` - BOM rainfall per area
- `flood_zones.csv` - historical flood risk, drainage capacity, elevation, lat/lng per area
- `population.csv` - CALD demographics per area

## Risk calculation

Each area gets a score from 0-100 based on 6 weighted factors: current water level (20%), rainfall (20%), flood history (20%), elevation (15%), drainage (15%), and community vulnerability (10%). If the water is rising fast the score gets a boost. Score >= 65 = DANGER, >= 40 = WARNING, else NORMAL.

The weights are rough, just to show the idea of combining multiple data sources. They can be changed in the `weights` dict in flask_api.py.

## For the Leaflet map

Two endpoints to choose from:

**`GET /risk_by_area`** - calculated risk per area (good for colour-coded markers):

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
    }, ...
  ]
}
```

For the map you need: `area`, `lat`, `lng`, `level`, `overall_score`. The rest is optional.

**`GET /data`** - raw data from all 4 CSVs (good if you want to show actual sensor readings, rainfall numbers, etc. directly):

```json
{
  "sensor_history": [{ "timestamp": "...", "water_level": "1.52", "rate_m_min": "0.12", ... }],
  "rainfall": [{ "date": "2026-05-16", "area": "Maribyrnong", "rainfall_mm": "24.2" }],
  "flood_zones": [{ "area": "Maribyrnong", "elevation_m": "8.5", "lat": "...", "lng": "...", ... }],
  "population": [{ "area": "Maribyrnong", "total_population": "3200", "cald_percentage": "42", ... }]
}
```

The lat/lng in `flood_zones.csv` are placeholders, update them if needed.

Poll every 10 seconds to keep in sync.
