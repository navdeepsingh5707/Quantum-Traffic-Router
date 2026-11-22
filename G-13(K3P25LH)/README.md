<p align="center">
  <img src="assets/logo.png" alt="Quantum Traffic Router" width="120">
</p>

<h1 align="center">Quantum Traffic Router</h1>

<p align="center">
  Splits cars across different routes so traffic jams less and trips get faster.
</p>

---

## About

Everyone takes the same "fastest" road, and it jams up while other roads stay empty.

This app spreads the cars over a few routes instead, so the total travel time goes down. Made for my CSE276 (AI Foundations) project.

## What it does

1. You enter a start and an end point (`latitude, longitude`).
2. It loads the real roads between them from OpenStreetMap.
3. It finds a few alternative routes.
4. It decides how many cars should take each route.
5. It compares three algorithms: **QPSO**, **PSO** and **GA**.
6. It shows tables, a graph and a map with the results.

## How it works

| Idea | In simple words |
|---|---|
| Road capacity | Every road type can only handle so many cars per hour |
| Delay | The more cars on a road, the slower it gets (BPR formula) |
| Optimizer | Tries many car splits like `[120, 80, 40]` and keeps the best one |
| Baseline | "Selfish" mode, where every car takes the shortest route |

## Screens

| Tab | What you see |
|---|---|
| Analytics & Results | Time saved, algorithm comparison, and cars per route |
| Convergence Dynamics | How fast each algorithm improves |
| Interactive Map | All routes on a map, coloured by traffic |

## How to run

You need Python 3, then:

```bash
pip install numpy networkx matplotlib pillow
python main.py
```

On Windows you can also double-click `run.bat`.

## Try it

These coordinates are already filled in when the app opens:

```
Origin:      31.6200, 74.8765
Destination: 31.6340, 74.8723
```

Click **Run Optimization**. No internet? Tick **Offline demo city mode**.

## Good to know

- Trip distance must be between 300 m and 14 km.
- Traffic is simulated, not live.
- Same input always gives the same result.

## Files

| File | What it does |
|---|---|
| `main.py` | Starts the app |
| `desktop_app.py` | The interface (panels, tables, tabs, map) |
| `traffic_core.py` | Road data, delay math, routes, QPSO / PSO / GA |
| `run.bat` | Double-click launcher for Windows |

## Built with

Python, Tkinter, NumPy, NetworkX, Matplotlib, Pillow and OpenStreetMap data.

Map data © OpenStreetMap contributors.
