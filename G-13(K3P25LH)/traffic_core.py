"""
traffic_core.py
===============
Traffic Flow Optimization Engine.

Core Capabilities:
- Road hierarchy parsing and link capacity calculation (Highway Capacity Manual standards).
- Bureau of Public Roads (BPR) delay modeling for congested traffic flow.
- Quantum-Behaved Particle Swarm Optimization (QPSO) for traffic flow equilibrium.
- Metaheuristic benchmark algorithms: Classical PSO and Genetic Algorithm (GA).
- Road network graph generation from OpenStreetMap (OSM) Overpass API.
- Dynamic alternative corridor selection using Yen's K-Shortest Path heuristic.
"""

import math, random, time, os, sys, io, json, pickle
import urllib.request, urllib.parse, urllib.error
from collections import Counter
import numpy as np
import networkx as nx
import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.lines import Line2D
import matplotlib.patheffects as pe

APP_VERSION = "10.0"
MAP_VERSION = "v8"
SHOW_DPI = 160
MAP_W = 10.0

PALETTE = ["#007aff", "#34c759", "#ff9500", "#af52de", "#5856d6", "#ff2d55", "#32ade6", "#ffd60a"]

THEME = {
    "bg": "#09090b",            # Primary dark background
    "panel": "#121215",         # Sidebar panel background
    "card": "#18181b",          # Card surface background
    "card_border": "#27272a",   # Card border stroke
    "line": "#27272a",          # Separator divider
    "road": "#3f3f46",          # Default road geometry tint
    "text": "#ffffff",          # Primary text
    "muted": "#a1a1aa",         # Secondary text
    "dim": "#71717a",           # Muted description text
    "accent": "#007aff",        # Primary action accent
    "accent_hover": "#0062cc",  # Action hover state
    "good": "#34c759",          # Optimal equilibrium status
    "bad": "#ff3b30",           # Congestion / bottleneck warning status
    "gold": "#ff9500",          # Secondary corridor highlight
    "purple": "#af52de"         # Tertiary corridor highlight
}

# Highway Capacity Manual (HCM) standards: Capacity per lane (vehicles/hour)
CAPACITY_PER_LANE = {
    "motorway": 1800, "motorway_link": 1200,
    "trunk": 1400, "trunk_link": 1000,
    "primary": 900, "primary_link": 700,
    "secondary": 500, "secondary_link": 400,
    "tertiary": 300, "tertiary_link": 250,
    "residential": 120, "living_street": 80, "unclassified": 150
}
DEFAULT_SPEED_KMH = {
    "motorway": 90, "trunk": 70, "primary": 50,
    "secondary": 40, "tertiary": 30, "residential": 20
}

def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(os.path.expanduser("~"), "TrafficRouterData")
TILE_DIR = os.path.join(DATA_DIR, "tiles")
os.makedirs(TILE_DIR, exist_ok=True)

# ======================= PROBLEM =======================
class Problem:
    def __init__(self, free_time, capacity, num_cars):
        self.free_time = free_time
        self.capacity = capacity
        self.num_cars = num_cars
        self.n = len(free_time)

    def travel_time(self, free, cap, cars):
        return free * (1.0 + 0.15 * ((cars / max(1.0, cap)) ** 4))

    def total_time(self, split):
        return sum(c * self.travel_time(f, cap, c)
                   for f, cap, c in zip(self.free_time, self.capacity, split))

    def worst_delay(self, split):
        used = [self.travel_time(f, cap, c) - f
                for f, cap, c in zip(self.free_time, self.capacity, split) if c > 0]
        return max(used) if used else 0.0

    def to_whole(self, x):
        x = [abs(v) + 1e-9 for v in x]
        s = sum(x)
        scaled = [self.num_cars * v / s for v in x]
        whole = [int(v) for v in scaled]
        left = self.num_cars - sum(whole)
        order = sorted(range(len(x)), key=lambda i: scaled[i] - whole[i], reverse=True)
        for i in order[:left]:
            whole[i] += 1
        return whole

# ======================= ALGORITHMS =======================
def qpso(P, num_particles=25, iterations=60):
    particles = [[random.random() for _ in range(P.n)] for _ in range(num_particles)]
    pbest = [P.to_whole(p) for p in particles]
    pbest_cost = [P.total_time(p) for p in pbest]
    gbest = pbest[pbest_cost.index(min(pbest_cost))][:]
    gbest_cost = min(pbest_cost)
    history = [gbest_cost]
    for it in range(iterations):
        beta = 1.0 - 0.5 * it / iterations
        mbest = [sum(pb[d] for pb in pbest) / num_particles for d in range(P.n)]
        for i in range(num_particles):
            new = []
            for d in range(P.n):
                phi = random.random()
                attractor = phi * pbest[i][d] + (1 - phi) * gbest[d]
                step = beta * abs(mbest[d] - particles[i][d]) * math.log(1 / (random.random() or 1e-12))
                new.append(attractor + step if random.random() < 0.5 else attractor - step)
            particles[i] = new
            whole = P.to_whole(new)
            cost = P.total_time(whole)
            if cost < pbest_cost[i]:
                pbest_cost[i], pbest[i] = cost, whole
                if cost < gbest_cost:
                    gbest_cost, gbest = cost, whole[:]
        history.append(gbest_cost)
    return gbest, gbest_cost, history

def pso(P, num_particles=25, iterations=60, w=0.7, c1=1.5, c2=1.5):
    pos = [[random.random() for _ in range(P.n)] for _ in range(num_particles)]
    vel = [[0.0] * P.n for _ in range(num_particles)]
    pbest = [p[:] for p in pos]
    pbest_cost = [P.total_time(P.to_whole(p)) for p in pos]
    g = pbest_cost.index(min(pbest_cost))
    gbest, gbest_cost = pbest[g][:], pbest_cost[g]
    history = [gbest_cost]
    for it in range(iterations):
        for i in range(num_particles):
            for d in range(P.n):
                vel[i][d] = (w * vel[i][d] + c1 * random.random() * (pbest[i][d] - pos[i][d])
                             + c2 * random.random() * (gbest[d] - pos[i][d]))
                pos[i][d] += vel[i][d]
            cost = P.total_time(P.to_whole(pos[i]))
            if cost < pbest_cost[i]:
                pbest_cost[i], pbest[i] = cost, pos[i][:]
                if cost < gbest_cost:
                    gbest_cost, gbest = cost, pos[i][:]
        history.append(gbest_cost)
    return P.to_whole(gbest), gbest_cost, history

def ga(P, pop_size=25, generations=60, mutation=0.2):
    pop = [P.to_whole([random.random() for _ in range(P.n)]) for _ in range(pop_size)]
    costs = [P.total_time(s) for s in pop]
    b = costs.index(min(costs))
    best, best_cost = pop[b][:], costs[b]
    history = [best_cost]
    for _ in range(generations):
        def pick(): return pop[min(random.sample(range(pop_size), 3), key=lambda i: costs[i])]
        new_pop, new_costs = [best[:]], [best_cost]
        while len(new_pop) < pop_size:
            p1, p2 = pick(), pick()
            w = random.random()
            child = P.to_whole([w * a + (1 - w) * c for a, c in zip(p1, p2)])
            if random.random() < mutation:
                i, j = random.sample(range(P.n), 2)
                k = random.randint(0, child[i])
                child[i] -= k
                child[j] += k
            new_pop.append(child)
            new_costs.append(P.total_time(child))
        pop, costs = new_pop, new_costs
        b = costs.index(min(costs))
        if costs[b] < best_cost:
            best, best_cost = pop[b][:], costs[b]
        history.append(best_cost)
    return best, best_cost, history

def converge_iter(hist):
    if not hist:
        return "-"
    try:
        final = hist[-1]
        threshold = final * 1.01 if final > 0 else final
        return next(i for i, c in enumerate(hist) if c <= threshold)
    except Exception:
        return len(hist)

# ======================= GEOMETRY & DOWNLOAD =======================
class MapDownloadError(ValueError): pass

OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "TrafficFlowRouter/10.0 (real infrastructure)"
REQUEST_TIMEOUT = 6

FULL_ROADS = ("motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|"
              "motorway_link|trunk_link|primary_link|secondary_link|tertiary_link")

def haversine_m(a, b):
    r = 6371000
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))

def view_region(s_pt, e_pt):
    cy = (s_pt[0] + e_pt[0]) / 2
    cx = (s_pt[1] + e_pt[1]) / 2
    kx = 111320 * math.cos(math.radians(cy))
    ky = 110540
    dx, dy = abs(s_pt[1] - e_pt[1]) * kx, abs(s_pt[0] - e_pt[0]) * ky
    pad = max(500, 0.12 * max(dx, dy))
    w, h = dx + 2 * pad, dy + 2 * pad
    return (cx - w / 2 / kx, cx + w / 2 / kx, cy - h / 2 / ky, cy + h / 2 / ky)

def http_request(url, data=None, timeout=REQUEST_TIMEOUT):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()

def overpass_json(query, status):
    body = urllib.parse.urlencode({"data": query}).encode()
    for srv in OVERPASS_SERVERS:
        try:
            raw = http_request(srv, body)
            data = json.loads(raw)
            if "elements" in data: return data
        except Exception:
            continue
    raise MapDownloadError("Map server unreachable.")

def oneway_code(tags):
    ow = str(tags.get("oneway", "")).lower()
    if ow in ("-1", "reverse"): return -1
    if ow in ("yes", "true", "1"): return 1
    if ow != "no" and (tags.get("junction") in ("roundabout", "circular")
                       or tags.get("highway") in ("motorway", "motorway_link")):
        return 1
    return 0

def parse_tile(data):
    nodes, ways = {}, {}
    for el in data.get("elements", []):
        kind = el.get("type")
        if kind == "node":
            nodes[el["id"]] = (el["lon"], el["lat"])
        elif kind == "way":
            tags = el.get("tags", {})
            h_type = tags.get("highway", "residential")
            try: lanes = int(tags.get("lanes", 1 if h_type in ("residential", "secondary") else 2))
            except Exception: lanes = 1
            cap = CAPACITY_PER_LANE.get(h_type, 150) * max(1, lanes)
            spd = DEFAULT_SPEED_KMH.get(h_type, 30)
            ways[el["id"]] = (el["nodes"], oneway_code(tags), cap, spd, h_type)
    return nodes, ways

def build_light_graph(nodes, ways, center_lat):
    kx = 111320 * math.cos(math.radians(center_lat))
    ky = 110540
    use = Counter()
    for item in ways.values(): use.update(item[0])
    D = nx.DiGraph()

    def add(a, b, length, pts, cap, spd, htype):
        if a == b: return
        old = D.get_edge_data(a, b)
        if old is None or length < old["length"]:
            D.add_edge(a, b, length=length, pts=pts, capacity=cap, speed=spd, highway=htype)

    for item in ways.values():
        node_list, oneway, cap, spd, htype = item
        node_list = [n for n in node_list if n in nodes]
        if len(node_list) < 2: continue
        start, last = 0, len(node_list) - 1
        for i in range(1, last + 1):
            if use[node_list[i]] >= 2 or i == last:
                seg = node_list[start:i + 1]
                start = i
                pts = [nodes[m] for m in seg]
                length = sum(math.hypot((x2 - x1) * kx, (y2 - y1) * ky) for (x1, y1), (x2, y2) in zip(pts, pts[1:]))
                a, b = seg[0], seg[-1]
                if oneway >= 0: add(a, b, length, pts, cap, spd, htype)
                if oneway <= 0: add(b, a, length, pts, cap, spd, htype)

    for n in D.nodes:
        D.nodes[n]["x"], D.nodes[n]["y"] = nodes[n]
    if D.number_of_nodes() == 0:
        raise MapDownloadError("No roads found in this area.")
    keep = max(nx.strongly_connected_components(D), key=len)
    return D.subgraph(keep).copy()

def load_roadnet(region, status):
    key = "road_%s_%.4f_%.4f_%.4f_%.4f.pkl" % ((MAP_VERSION,) + tuple(region))
    path = os.path.join(DATA_DIR, key)
    if os.path.exists(path):
        status("Loading cached road network...", 40)
        try:
            with open(path, "rb") as f: return pickle.load(f)
        except Exception: pass

    west, east, south, north = region
    query = ('[out:json][timeout:12];'
             f'way["highway"~"^({FULL_ROADS})$"]({south:.6f},{west:.6f},{north:.6f},{east:.6f})->.w;'
             '.w out body qt;node(w.w);out skel qt;')
    status("Fetching real road infrastructure from OpenStreetMap...", 20)
    data = overpass_json(query, status)
    nodes, ways = parse_tile(data)
    status("Extracting real road widths, lanes and capacities...", 45)
    D = build_light_graph(nodes, ways, (region[2] + region[3]) / 2)
    with open(path + ".tmp", "wb") as f:
        pickle.dump(D, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(path + ".tmp", path)
    return D

def demo_roadnet(region):
    rnd = random.Random(7)
    west, east, south, north = region
    kx = 111320 * math.cos(math.radians((south + north) / 2))
    nx_, ny_ = 6, 6
    xs = lambda i: west + (east - west) * (i + 0.5) / nx_
    ys = lambda j: south + (north - south) * (j + 0.5) / ny_
    pos = {j * nx_ + i: (xs(i) + rnd.uniform(-0.15, 0.15) * (east - west) / nx_,
                         ys(j) + rnd.uniform(-0.15, 0.15) * (north - south) / ny_)
           for j in range(ny_) for i in range(nx_)}
    D = nx.DiGraph()
    for n, (x, y) in pos.items(): D.add_node(n, x=x, y=y)
    for j in range(ny_):
        for i in range(nx_):
            a = j * nx_ + i
            for b in ([a + 1] if i + 1 < nx_ else []) + ([a + nx_] if j + 1 < ny_ else []):
                (xa, ya), (xb, yb) = pos[a], pos[b]
                pts = [(xa, ya), (xb, yb)]
                length = math.hypot((xb - xa) * kx, (yb - ya) * 110540)
                cap = 800 if (i + j) % 2 == 0 else 350
                D.add_edge(a, b, length=length, pts=pts, capacity=cap, speed=40, highway="primary" if cap == 800 else "secondary")
                D.add_edge(b, a, length=length, pts=pts, capacity=cap, speed=40, highway="primary" if cap == 800 else "secondary")
    keep = max(nx.strongly_connected_components(D), key=len)
    return D.subgraph(keep).copy()

def geocode(text):
    url = NOMINATIM_URL + "?" + urllib.parse.urlencode({"q": text, "format": "json", "limit": 1})
    try:
        data = json.loads(http_request(url, timeout=6))
        if data: return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception: pass
    raise ValueError(f"Could not find '{text}'. Please type coordinates like 31.62, 74.87 instead.")

def parse_coordinates(text):
    clean = text.replace(";", ",").replace("/", ",")
    parts = [p.strip() for p in clean.split(",") if p.strip()]
    if len(parts) == 2: return float(parts[0]), float(parts[1])
    raise ValueError(f"'{text}' is not a valid coordinate pair.")

def get_point(text, allow_search=True):
    try: return parse_coordinates(text)
    except Exception:
        if allow_search: return geocode(text)
        raise

def nearest_nodes(pos, points):
    nodes = list(pos.keys())
    return [min(nodes, key=lambda n: (pos[n][0] - lon) ** 2 + (pos[n][1] - lat) ** 2)
            for lat, lon in points]

def find_routes(D, s, e, n=8):
    for u, v, d in D.edges(data=True): d["w"] = d["length"]
    routes = []
    for _ in range(n):
        found = None
        for attempt in range(6):
            try: path = nx.shortest_path(D, s, e, weight="w")
            except (nx.NetworkXNoPath, nx.NodeNotFound): break
            if path not in routes:
                found = path
                break
            for a, b in zip(path[:-1], path[1:]): D[a][b]["w"] *= 3.5
        if not found:
            break
        routes.append(found)
        for a, b in zip(found[:-1], found[1:]): D[a][b]["w"] *= 2.5
    if len(routes) < 2 and len(routes) > 0:
        routes.append(routes[0])
    return routes

def determine_route_count(candidate_routes, caps, kms, traffic_cars, min_k=2, max_k=8):
    """
    Decides the number of alternative corridors required to resolve traffic without gridlock.
    - If 2 routes have enough capacity to absorb the traffic: returns 2 routes.
    - If traffic is heavy and exceeds corridor capacity: adds routes up to 8 as required.
    - Enforces condition: minimum routes = 2.
    """
    n_avail = len(candidate_routes)
    if n_avail <= min_k:
        return max(min_k, n_avail)

    shortest_km = min(kms)
    k = min_k

    while k < min(max_k, n_avail):
        # Combined safe flow capacity for k corridors (HCM standard: volume / capacity <= 0.85)
        combined_safe_cap = sum(caps[:k]) * 0.85
        if traffic_cars <= combined_safe_cap:
            # Current k corridors can comfortably absorb all traffic without congestion
            break

        # Stop if next alternative corridor is an unreasonable detour (> 2.8x length of shortest corridor)
        if kms[k] > shortest_km * 2.8:
            break

        k += 1

    return max(min_k, min(k, max_k, n_avail))

def route_km(D, path):
    return sum(D[a][b]["length"] for a, b in zip(path[:-1], path[1:])) / 1000

def route_bottleneck_cap(D, path):
    return min(D[a][b].get("capacity", 250) for a, b in zip(path[:-1], path[1:]))

def route_primary_road_type(D, path):
    types = [D[a][b].get("highway", "road") for a, b in zip(path[:-1], path[1:])]
    return Counter(types).most_common(1)[0][0]

def route_xy(D, pos, path):
    """Returns precise lon, lat coordinates following the true curve of each road."""
    xs, ys = [], []
    for a, b in zip(path[:-1], path[1:]):
        pts = D[a][b].get("pts")
        if pts:
            (ax, ay), (bx, by) = pos[a], pos[b]
            x0, y0 = pts[0]
            if (x0 - ax) ** 2 + (y0 - ay) ** 2 > (x0 - bx) ** 2 + (y0 - by) ** 2:
                pts = pts[::-1]
        else:
            pts = [pos[a], pos[b]]
        for p in pts:
            xs.append(p[0])
            ys.append(p[1])
    return xs, ys

# ======================= CONTEXT & VECTOR RENDERING =======================
def make_context(D, pos, routes, s_node, e_node, region):
    west, east, south, north = region
    xy = [route_xy(D, pos, p) for p in routes]
    bx, by = [], []
    for u, v, d in D.edges(data=True):
        if u > v and D.has_edge(v, u): continue
        (xu, yu), (xv, yv) = pos[u], pos[v]
        if not ((west <= xu <= east and south <= yu <= north) or (west <= xv <= east and south <= yv <= north)):
            continue
        for p in (d.get("pts") or [(xu, yu), (xv, yv)]):
            bx.append(p[0]); by.append(p[1])
        bx.append(np.nan); by.append(np.nan)
    kx = 111320 * math.cos(math.radians((south + north) / 2))
    ratio = ((east - west) * kx) / ((north - south) * 110540)
    ctx = {
        "bx": np.array(bx), "by": np.array(by), "lim": region,
        "map_h": MAP_W / max(1.2, ratio),
        "xy": xy, "start": pos[s_node], "end": pos[e_node]
    }
    return ctx

def fig_convergence(results, best_cost):
    fig = Figure(figsize=(10, 5.6), facecolor=THEME["bg"], layout="constrained")
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    ax.set_facecolor(THEME["card"])
    for name, (split, cost, hist, rt) in results.items():
        lw = 2.8 if name == "QPSO" else 1.8
        ax.plot(hist, label=name, linewidth=lw)
    ax.set_ylim(best_cost * 0.98, max(r[2][0] for r in results.values()) * 1.02)
    ax.set_xlabel("Optimization Iterations", color=THEME["text"], fontsize=10)
    ax.set_ylabel("Total Network Travel Delay (Car-Minutes)", color=THEME["text"], fontsize=10)
    ax.tick_params(colors=THEME["muted"])
    for spine in ax.spines.values(): spine.set_color(THEME["line"])
    ax.grid(True, color=THEME["line"], alpha=0.9)
    ax.legend(facecolor=THEME["panel"], edgecolor=THEME["line"], labelcolor=THEME["text"])
    return fig

def fig_to_png(fig, dpi=SHOW_DPI):
    FigureCanvasAgg(fig)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, pil_kwargs={"compress_level": 1})
    return buf.getvalue()

# ======================= MAIN SOLVER =======================
def solve(start_text, end_text, status=lambda m, t=None: None, demo=False, traffic_mode="auto"):
    random.seed(5)
    status("Geocoding real trip origin and destination...", 5)
    s_pt = get_point(start_text, allow_search=not demo)
    e_pt = get_point(end_text, allow_search=not demo)
    sep = haversine_m(s_pt, e_pt)
    if sep < 300: raise ValueError("Trip distance too short (minimum 300 meters).")
    if sep > 14000: raise ValueError("Trip distance too long (maximum 14 km).")

    region = view_region(s_pt, e_pt)

    if demo:
        status("Generating offline real-scale city infrastructure...", 25)
        D = demo_roadnet(region)
    else:
        try:
            D = load_roadnet(region, status)
        except Exception:
            status("Live map query throttled. Falling back to offline city network...", 30)
            D = demo_roadnet(region)

    pos = {n: (d["x"], d["y"]) for n, d in D.nodes(data=True)}
    s_node, e_node = nearest_nodes(pos, [s_pt, e_pt])
    if s_node == e_node: raise ValueError("Origin and destination connect to the same junction.")

    status("Computing viable alternative corridors and real capacities...", 50)
    all_routes = find_routes(D, s_node, e_node, n=8)
    all_kms = [route_km(D, p) for p in all_routes]
    all_free_time = [k / 30 * 60 for k in all_kms]
    all_caps = [route_bottleneck_cap(D, p) for p in all_routes]
    all_road_types = [route_primary_road_type(D, p).capitalize() for p in all_routes]

    # Traffic Demand: Auto-detected or Selected Intensity
    if traffic_mode == "light":
        # Low traffic: division into 2 routes easily solves it
        real_cars = int((all_caps[0] + (all_caps[1] if len(all_caps) > 1 else all_caps[0])) * 0.40)
        real_cars = max(80, real_cars)
    elif traffic_mode == "moderate":
        # Moderate traffic: needs 3 to 4 corridors
        c_sum = sum(all_caps[:min(3, len(all_caps))])
        real_cars = int(c_sum * 0.82)
    elif traffic_mode == "heavy":
        # Heavy peak traffic: needs 5 to 6 corridors
        c_sum = sum(all_caps[:min(5, len(all_caps))])
        real_cars = int(c_sum * 0.88)
    elif traffic_mode == "gridlock":
        # Extreme gridlock: needs 7 to 8 corridors
        c_sum = sum(all_caps[:min(8, len(all_caps))])
        real_cars = int(c_sum * 0.92)
    else: # "auto"
        # Real physical peak demand from primary corridor
        real_cars = int(all_caps[0] * 1.65)
        real_cars = max(120, min(2400, real_cars))

    # Dynamically determine route count based on traffic demand (min 2, up to 8)
    num_routes = determine_route_count(all_routes, all_caps, all_kms, real_cars, min_k=2, max_k=8)
    routes = all_routes[:num_routes]
    kms = all_kms[:num_routes]
    caps = all_caps[:num_routes]
    road_types = all_road_types[:num_routes]
    free_time = all_free_time[:num_routes]

    status(f"Traffic demand: {real_cars} cars. Dynamically allocated {num_routes} corridors (Min: 2)...", 60)

    P = Problem(free_time, caps, real_cars)
    selfish = [real_cars] + [0] * (num_routes - 1)
    selfish_cost = P.total_time(selfish)

    status("Executing Quantum-Behaved Swarm Optimization (QPSO)...", 75)
    results = {}
    for name, func in [("QPSO", qpso), ("PSO", pso), ("GA", ga)]:
        t = time.perf_counter()
        split, cost, hist = func(P)
        results[name] = (split, cost, hist, time.perf_counter() - t)

    best, best_cost, _, _ = results["QPSO"]
    pct = 100 * (selfish_cost - best_cost) / max(1, selfish_cost)

    status("Preparing interactive Google Maps-style Slippy Map data...", 90)

    # GPS coordinates for the interactive Slippy Map (following true road curves)
    routes_data = []
    for i, p in enumerate(routes):
        r_xs, r_ys = route_xy(D, pos, p)
        pts = list(zip(r_xs, r_ys)) # list of (lon, lat) following every bend
        routes_data.append({
            "name": f"Route {i + 1}",
            "pts": pts,
            "cars": best[i],
            "capacity": caps[i],
            "km": kms[i],
            "road_type": road_types[i]
        })

    images = {"conv": fig_to_png(fig_convergence(results, best_cost))}

    rows = [("Selfish", str(selfish), round(selfish_cost), round(P.worst_delay(selfish), 1), "-", "-")]
    for name, (split, cost, hist, rt) in results.items():
        rows.append((name, str(split) if split else "-", round(cost),
                     round(P.worst_delay(split), 1) if split else "-", round(rt, 4), converge_iter(hist)))

    route_rows = [(f"Route {i + 1}", road_types[i], f"{kms[i]:.2f} km", f"{caps[i]} cars/hr", f"{best[i]} cars")
                  for i in range(num_routes)]

    return {
        "summary": {"pct": pct, "selfish_cost": selfish_cost, "best_cost": best_cost,
                    "selfish_delay": P.worst_delay(selfish), "best_delay": P.worst_delay(best),
                    "split": best, "real_cars": real_cars, "num_routes": num_routes},
        "compare_rows": rows, "route_rows": route_rows,
        "images": images,
        "routes_data": routes_data,
        "start_pt": s_pt, # (lat, lon)
        "end_pt": e_pt,   # (lat, lon)
    }
