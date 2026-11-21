Quantum Traffic Router

Ever notice how everyone takes the same road, and then that road jams up while the other roads sit empty?

This app tries to fix that. You give it a start and an end point, and instead of sending every car down the single shortest route, it splits the cars across several routes so the total travel time goes down.

It's a desktop app (Tkinter, dark theme) built for my CSE276 AI Foundations project.

What it does
You enter an origin and a destination (as latitude, longitude).
It gets the real road network between them from OpenStreetMap.
It finds up to 8 alternative routes between the two points.
It simulates a bunch of cars and asks: how many cars should go on each route so everyone gets there fastest overall?
It solves that with three algorithms and compares them:
QPSO (Quantum-behaved Particle Swarm Optimization), the main one
PSO (normal Particle Swarm Optimization)
GA (Genetic Algorithm)
It shows you the results as tables, a graph, and an interactive map.

The "selfish" baseline in the results is what happens when every car just takes the shortest route. That's what we compare against.

How it works (the simple version)
Roads have limits. Each road type (motorway, primary, residential...) has a capacity in cars per hour, based on Highway Capacity Manual numbers. A route is only as good as its narrowest road.
More cars means slower travel. Delay is calculated with the BPR formula: time = free_time × (1 + 0.15 × (cars / capacity)^4). Below capacity it barely matters, above capacity it explodes.
The optimizers search for the best split. Each particle (or GA individual) is one guess like [120, 80, 40] cars across 3 routes. The algorithm keeps improving the guesses until total travel time stops dropping.
Number of routes is automatic. Light traffic uses 2 routes. Heavy traffic can use up to 8. It stops adding routes if the next one is a huge detour (more than 2.8x the shortest route).
What you see in the app

Left panel

Origin and destination boxes
Traffic intensity (Auto, Light, Moderate, Heavy, Extreme Gridlock)
Offline demo mode checkbox
The Run Optimization button

Right side, 3 tabs

Analytics & Results: 4 summary cards (time saved, traffic load, selfish delay, QPSO delay), an algorithm comparison table, and a table of each corridor with its road type, length, capacity and how many cars QPSO sent there
Convergence Dynamics: a graph showing how fast QPSO, PSO and GA improve over iterations
Interactive Slippy Map: a zoomable, draggable map with all the routes drawn on it, coloured by traffic load
Setup

You need Python 3 and these libraries:

pip install numpy networkx matplotlib pillow

Tkinter comes with the normal Python installer on Windows, so you shouldn't need to install it separately.

Running it

Easiest way (Windows): double-click run.bat.

Or from a terminal:

python main.py

If something is missing, main.py shows a startup error telling you which library to install.

Quick try

The app opens with these coordinates already filled in:

Origin:      31.6200, 74.8765
Destination: 31.6340, 74.8723

Just click Run Optimization.

No internet? Tick Offline demo city mode first. It generates a fake city road network so you can still test everything.

Good to know
Trip distance must be between 300 m and 14 km. Shorter or longer than that and it will show an error.
No internet or the map server is slow? The app automatically falls back to the offline demo city.
Traffic is simulated, not live. The number of cars is estimated from road capacity and the traffic intensity you pick. It doesn't read real-time traffic from Google or anywhere else.
Free-flow time assumes 30 km/h for every route, to keep things simple.
Results are repeatable. The random seed is fixed, so the same input gives the same output every time.
Map tiles and downloaded road data are cached in a TrafficRouterData folder in your user directory, so repeat runs are faster.
Project files
File	What it does
main.py	Starts the app. Sets up high-DPI on Windows and checks the imports work
desktop_app.py	The whole interface: panels, buttons, tables, tabs, and the slippy map
traffic_core.py	The brain: road data, capacity and delay math, route finding, QPSO / PSO / GA
run.bat	Double-click launcher for Windows
Built with

Python, Tkinter, NumPy, NetworkX, Matplotlib, Pillow, and map data from OpenStreetMap (Overpass and Nominatim).

Map data © OpenStreetMap contributors.

Why "quantum"?

It isn't running on a quantum computer. QPSO is a particle swarm algorithm inspired by how particles behave in quantum mechanics: instead of moving with a fixed velocity, each particle jumps around its best-known position with some randomness. That tends to help it explore more and avoid getting stuck.
