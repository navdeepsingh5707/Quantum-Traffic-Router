"""
main.py
=======
Quantum Traffic Router.
Application entry point and GUI lifecycle initializer.

Responsibilities:
- Configure per-monitor DPI awareness for high-resolution displays on Windows.
- Validate required runtime dependencies (NumPy, NetworkX, Matplotlib, Pillow).
- Instantiate and run the main Tkinter application event loop.
"""
import sys, os, ctypes

# Configure Windows Per-Monitor DPI awareness to enable native hardware resolution
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

try:
    import tkinter as tk
    from tkinter import messagebox
except ImportError as e:
    print(f"Tkinter error: {e}")
    sys.exit(1)

try:
    from desktop_app import TrafficRouterApp
except Exception as err:
    print("\n" + "="*60)
    print("STARTUP ERROR:")
    print(err)
    print("="*60)
    import traceback
    traceback.print_exc()
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Startup Error",
            f"Could not load application.\n\nError: {err}\n\nPlease verify that required libraries are installed:\npip install numpy networkx matplotlib pillow"
        )
    except Exception:
        pass
    input("\nPress Enter to exit...")
    sys.exit(1)

def main():
    root = tk.Tk()
    TrafficRouterApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
