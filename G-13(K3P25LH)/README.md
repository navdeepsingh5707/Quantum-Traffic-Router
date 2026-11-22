<p align="center">
  <img src="assets/logo.png" alt="Quantum Traffic Router logo" width="140">
</p>

<h1 align="center">Quantum Traffic Router</h1>

<p align="center">
  A desktop app that splits cars across several routes, so traffic jams less and trips get faster.
</p>

---

## Why I built this

Everyone's GPS sends them down the same "fastest" road. Then that road jams up while the other roads sit empty.

This app tries a different idea: instead of sending every car down the shortest route, **spread them over a few routes** so the total travel time goes down. It was my project for CSE276 (AI Foundations).

## What it does

1. You enter an **origin** and a **destination** (`latitude, longitude`).
2. It downloads the real road network between them from OpenStreetMap.
3. It finds up to 8 alternative routes.
4. It simulates a group of cars and works out **how many cars should take each route**.
5. It solves this with three algorithms and compares them:
   - **QPSO** (Quantum-behaved Particle Swarm Optimization), the main one
   - **PSO** (Particle Swarm Optimization)
   - **GA** (Genetic Algorithm)
6. It shows the results as tables, a graph, and an interactive map.

The "selfish" baseline is what happens when every car just takes the shortest route. That's what the results are compared against.

## How it works (simple version)

- **Roads have limits.** Each road type (motorway, primary, residential...) has a capacity in cars per hour, based on Highway Capacity Manual numbers. A route is only as good as its narrowest road.
- **More cars means slower travel.** Delay uses the BPR formula: `time = free_time × (1 + 0.15 × (cars / capacity)^4)`. Under capacity it barely matters. Over capacity it blows up.
- **The optimizers look for the best split.** One guess looks like `[120, 80, 40]` (cars on route 1, 2, 3). The algorithm keeps improving its guesses until total travel time stops dropping.
- **Number of routes is automatic.** Light traffic uses 2 routes, heavy traffic can use up to 8. It stops adding routes if the next one is a huge detour (more than 2.8x the shortest route).

## What you see in the app

**Left panel:** origin and destination boxes, traffic intensity (Auto, Light, Moderate, Heavy, Extreme Gridlock), offline demo mode, and the **Run Optimization** button.

**Right side, 3 tabs:**
- **Analytics & Results**: summary cards, an algorithm comparison table, and a table of every corridor with road type, length, capacity and the cars QPSO sent there
- **Convergence Dynamics**: a graph of how fast QPSO, PSO and GA improve
- **Interactive Slippy Map**: a zoomable map with all the routes drawn on it, coloured by traffic load

## Getting started

You need **Python 3**. Tkinter comes with the normal Windows installer.

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
pip install -r requirements.txt
python main.py
```

On Windows you can also just double-click `run.bat`.

## Try it

The app opens with these coordinates already filled in:

```
Origin:      31.6200, 74.8765
Destination: 31.6340, 74.8723
```

Click **Run Optimization**. No internet? Tick **Offline demo city mode** first and it will generate a fake city so you can still test everything.

## Build an .exe (Windows)

```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --icon=assets/logo.ico --name "QuantumTrafficRouter" main.py
```

Your exe will be in the `dist` folder.

## Good to know

- Trip distance must be between **300 m and 14 km**.
- If there's no internet or the map server is slow, it falls back to the offline demo city.
- **Traffic is simulated, not live.** Car counts are estimated from road capacity and the intensity you pick. It doesn't read real-time traffic data.
- Free-flow time assumes **30 km/h** on every route, to keep things simple.
- Results are repeatable. The random seed is fixed, so the same input gives the same output.
- Downloaded road data and map tiles are cached in a `TrafficRouterData` folder in your user directory.

## Project structure

```
.
├── main.py            # starts the app
├── desktop_app.py     # the whole interface (panels, tables, tabs, map)
├── traffic_core.py    # road data, delay math, route finding, QPSO / PSO / GA
├── run.bat            # double-click launcher for Windows
├── requirements.txt
└── assets/
    ├── logo.png
    └── logo.ico
```

## Why "quantum"?

It doesn't run on a quantum computer. QPSO is a particle swarm algorithm inspired by how particles behave in quantum mechanics. Instead of moving with a fixed velocity, each particle jumps around its best-known position with some randomness. That helps it explore more and avoid getting stuck.

## Built with

Python, Tkinter, NumPy, NetworkX, Matplotlib, Pillow, and map data from OpenStreetMap (Overpass and Nominatim).

Map data © OpenStreetMap contributors.
