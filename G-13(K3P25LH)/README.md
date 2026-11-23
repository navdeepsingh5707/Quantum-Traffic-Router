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

1. You enter a start and an end point (a place name or coordinates).
2. It gets real driving routes between them from OpenStreetMap routing servers.
3. It keeps the 2 to 5 best alternative routes.
4. It decides how many cars should take each route.
5. It compares three algorithms: **QPSO**, **PSO** and **GA**.
6. It shows tables, a graph and an interactive map with the results.

## How it works

| Idea | In simple words |
|---|---|
| Real routes | Route shapes and travel times come from live OpenStreetMap routing servers |
| Road capacity | Each route gets a capacity (cars per hour) based on how fast its roads are: highway, primary road, city arterial or local street |
| Number of cars | Worked out automatically from the total capacity of the routes |
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
In the left panel, fill in the **ORIGIN** and **DESTINATION** boxes. You can do it two ways:

**A. Type a place name**
1. Start typing, for example `Lovely Professional University`.
2. A list of suggestions with a 📍 pin appears.
3. Click one, or use the **↑ ↓** keys and press **Enter**.
4. The box fills with the coordinates of that place.

**B. Type coordinates**

| Box | Example |
|---|---|
| Origin | `31.6200, 74.8765` |
| Destination | `31.6340, 74.8723` |

Format: `latitude, longitude` with a comma between them.

**How to get coordinates:** open Google Maps, right-click any place, and click the numbers at the top of the menu to copy them. Paste them into the box.

> Place search only shows places in **India**. For other countries, use coordinates.

### Step 2: Choose online or offline
- **Normal mode (default):** gets real routes from the internet. Needs internet.
- **Offline demo city mode (checkbox):** makes sample curved routes between your two points, so you can test the app without real roads. Use **coordinates** in this mode, because place search is turned off.

### Step 3: Click RUN OPTIMIZATION
The progress bar and the status text under the button show what the app is doing. Wait until it says **Optimization complete**.

### Quick test
Type these coordinates and click **RUN OPTIMIZATION**:

```
Origin:      31.6200, 74.8765
Destination: 31.6340, 74.8723
```

---

## How to read the results

**Analytics & Results tab**
- **Summary cards:** how much time is saved and the delay with and without optimization.
- **Algorithm benchmark table:** compares QPSO, PSO and GA. Lower travel time is better. "Selfish" is the baseline where everyone takes the shortest route.
- **Corridor table:** every route with its road type, length, capacity, and how many cars QPSO sent on it.

**Convergence Dynamics tab**
A graph showing how quickly each algorithm improves. A line that drops fast and then flattens means it found a good answer.

**Interactive Slippy Map tab**
A map you can zoom and drag. All routes are drawn on it side by side, so you can see routes that share the same road. Use the toggle at the top right to switch between street map and satellite view.

---

## Rules to remember

- Origin and destination must be **between 300 m and 25 km** apart.
- Normal mode needs **internet** (for routes, place search and map tiles).
- Traffic is **simulated**, not live. The number of cars is estimated from road capacity.
- If the routing servers are busy or down, the app uses **estimated curved routes** instead of real roads. The status text tells you when this happens.
- Map pictures you have already viewed are saved in a `TrafficRouterData` folder in your user folder.

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
| No suggestions when typing a place | Check your internet, or type coordinates. Search only works for places in India |
| "Could not find ..." message | Use coordinates like `31.62, 74.87` instead of a place name |
| Distance error | Pick two points between 300 m and 25 km apart |
| Routes look smooth and curved, not like real roads | The routing servers were busy, so estimated routes were used. Run it again in a minute |
| Stuck or slow on loading | The routing server is slow. Wait a bit, or tick **Offline demo city mode** |

---

## Files

| File | What it does |
|---|---|
| `main.py` | Starts the app |
| `desktop_app.py` | The interface (panels, tables, tabs, map, place search) |
| `traffic_core.py` | Route fetching, delay math, QPSO / PSO / GA |
| `run.bat` | Double-click launcher for Windows |
| `assets/` | Logo files |

## Built with

Python, Tkinter, NumPy, NetworkX, Matplotlib, Pillow, and OpenStreetMap data (routing, place search and map tiles).

Map data © OpenStreetMap contributors.
