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

1. You enter a start and an end point.
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

---

## Setup (do this once)

### 1. Install Python
Download Python 3 from [python.org](https://www.python.org/downloads/). On the first installer screen, tick **"Add Python to PATH"**, then install.

To check it worked, open a terminal and type:
```bash
python --version
```

### 2. Download the project
```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
```
Or click the green **Code** button on GitHub, choose **Download ZIP**, and unzip it.

### 3. Install the libraries
```bash
pip install numpy networkx matplotlib pillow
```

---

## Start the app

### Option 1: double-click `run.bat` (Windows)

You don't need a terminal. Open the app straight from File Explorer.

1. Open the project folder in **File Explorer**. If you downloaded a ZIP, right-click it and choose **Extract All** first. Don't run `run.bat` from inside the ZIP.
2. Find the file named `run.bat`.
3. **Double-click** it.
4. The app window opens. There is no black terminal window, this is normal.

**Make a desktop shortcut (optional)**
1. Right-click `run.bat`.
2. Choose **Show more options → Send to → Desktop (create shortcut)**.
3. To give it the logo: right-click the shortcut, choose **Properties → Change Icon... → Browse...**, select `assets/logo.ico`, and click **OK**.

> Keep `run.bat` inside the project folder. If you move only the file, the app won't start. Use a shortcut instead.

### Option 2: use the terminal
```bash
python main.py
```
Use this one if you want to see error messages.

---

## How to use the app

### Step 1: Enter your trip
In the left panel, fill in the two boxes:

| Box | What to type | Example |
|---|---|---|
| Origin | Where the trip starts | `31.6200, 74.8765` |
| Destination | Where the trip ends | `31.6340, 74.8723` |

**Coordinates format:** `latitude, longitude` with a comma between them.

**How to get coordinates:** open Google Maps, right-click any place, and click the numbers at the top of the menu to copy them. Paste them into the box.

You can also type a place name, like `Lovely Professional University`. This needs internet, and coordinates are more reliable.

### Step 2: Pick the traffic level

| Option | Meaning |
|---|---|
| Auto | The app decides the traffic level itself |
| Light | Few cars, so roads are mostly empty |
| Moderate | Normal daily traffic |
| Heavy | Rush hour |
| Extreme Gridlock | Roads are completely packed |

Heavier traffic means more cars, and the app uses more routes to spread them out.

### Step 3: Choose online or offline
- **Normal mode:** downloads the real roads from OpenStreetMap. Needs internet.
- **Offline demo city mode (checkbox):** makes a fake city, so it works without internet. Good for testing or if the map server is slow. Use coordinates in this mode.

### Step 4: Click Run Optimization
The status text under the button shows what the app is doing. The first run for a new area can take a while because it downloads road data. After that it is saved, so repeat runs are faster.

### Quick test
These coordinates are already filled in when the app opens. Just click **Run Optimization**.

```
Origin:      31.6200, 74.8765
Destination: 31.6340, 74.8723
```

---

## How to read the results

**Analytics & Results tab**
- **Summary cards:** time saved, traffic load, delay when everyone takes the shortest route ("selfish"), and delay with QPSO.
- **Algorithm table:** compares QPSO, PSO and GA. Lower delay is better.
- **Corridor table:** every route with its road type, length, capacity, and how many cars QPSO sent on it.

**Convergence Dynamics tab**
A graph showing how quickly each algorithm improves. A line that drops fast and then flattens means it found a good answer.

**Interactive Map tab**
A map you can zoom and drag. All routes are drawn on it and coloured by how busy they are.

---

## Rules to remember

- Origin and destination must be **between 300 m and 14 km** apart.
- Traffic is **simulated**, not live.
- The same input gives the same result every time.

---

## Problems and fixes

| Problem | Fix |
|---|---|
| `'python' is not recognized` | Python is not in PATH. Reinstall it and tick **Add Python to PATH** |
| `ModuleNotFoundError` | A library is missing. Run `pip install numpy networkx matplotlib pillow` |
| Tkinter error | Reinstall Python from python.org (the normal installer includes Tkinter) |
| Nothing happens when you double-click `run.bat` | Open a terminal in the project folder and run `python main.py` to see the exact error |
| "Windows protected your PC" | Click **More info**, then **Run anyway**. This is normal for .bat files from the internet |
| `run.bat` shows as just `run` | In File Explorer click **View → Show → File name extensions** |
| "Startup Error" box | Run `pip install numpy networkx matplotlib pillow` and try again |
| "Could not find ..." message | Use coordinates like `31.62, 74.87` instead of a place name |
| Distance error | Pick two points between 300 m and 14 km apart |
| Stuck or slow on loading | The map server is busy. Wait a bit, or tick **Offline demo city mode** |

---

## Files

| File | What it does |
|---|---|
| `main.py` | Starts the app |
| `desktop_app.py` | The interface (panels, tables, tabs, map) |
| `traffic_core.py` | Road data, delay math, routes, QPSO / PSO / GA |
| `run.bat` | Double-click launcher for Windows |
| `assets/` | Logo files |

## Built with

Python, Tkinter, NumPy, NetworkX, Matplotlib, Pillow and OpenStreetMap data.

Map data © OpenStreetMap contributors.
