#!/usr/bin/env python3
import os
import math
import statistics
import hashlib

from osrparse import Replay
import matplotlib.pyplot as plt


# ========= .osu parsing =========

def parse_hitobjects(osu_path):
    """Return a list of (time_ms, x, y) for standard hitobjects."""
    hitobjects = []
    with open(osu_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    in_hitobjects = False
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("[HitObjects]"):
            in_hitobjects = True
            continue
        if not in_hitobjects:
            continue

        parts = line.split(",")
        if len(parts) < 3:
            continue
        try:
            x = int(parts[0])
            y = int(parts[1])
            t = int(parts[2])
        except ValueError:
            continue

        hitobjects.append((t, x, y))

    return hitobjects


# ========= replay timeline =========

def build_replay_timeline(replay):
    """Build a timeline of (time_ms, x, y) from a Replay object."""
    timeline = []
    t = 0
    for evt in replay.replay_data:
        # Compatibility with different osrparse versions
        dt = getattr(evt, "time_since_previous_action", None)
        if dt is None:
            dt = getattr(evt, "time_delta", 0)

        t += dt
        timeline.append((t, evt.x, evt.y))

    return timeline


def find_closest_frame(timeline, target_time, max_delta=80):
    """Find the replay frame closest to a given time."""
    best = None
    best_dt = None
    for t, x, y in timeline:
        dt = abs(t - target_time)
        if best_dt is None or dt < best_dt:
            best_dt = dt
            best = (t, x, y)
        if t > target_time and best_dt is not None and t - target_time > best_dt:
            break

    if best is None or best_dt is None or best_dt > max_delta:
        return None
    return best


# ========= MD5 helpers =========

def md5_file(path):
    """Return the MD5 hash of a file."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def find_osu_by_md5(songs_folder, md5_hash):
    """Search for a .osu file in Songs/ matching the given MD5 hash."""
    for root, dirs, files in os.walk(songs_folder):
        for name in files:
            if not name.lower().endswith(".osu"):
                continue
            path = os.path.join(root, name)
            try:
                if md5_file(path) == md5_hash:
                    return path
            except Exception:
                continue
    return None


# ========= analysis per replay =========

def analyze_replay_with_md5(osr_path, songs_folder, include_radius=80.0):
    """
    Analyze a single .osr file:
    - read its beatmap MD5
    - locate the corresponding .osu in Songs
    - calculate aim errors (dx, dy) in osu! pixels.
    """
    print(f"\n[+] Analyzing replay: {osr_path}")

    if not os.path.exists(osr_path):
        print(f"  [ERROR] Replay not found: {osr_path}")
        return []

    try:
        replay = Replay.from_path(osr_path)
    except Exception as e:
        print(f"  [ERROR] Failed to load replay: {e}")
        return []

    beatmap_hash = getattr(replay, "beatmap_hash", None)
    if not beatmap_hash:
        beatmap_hash = getattr(replay, "beatmap_md5", None)

    if not beatmap_hash:
        print("  [ERROR] No beatmap MD5/hash found in replay.")
        return []

    osu_path = find_osu_by_md5(songs_folder, beatmap_hash)
    if not osu_path:
        print("  [ERROR] Could not find matching .osu in Songs/ for this replay.")
        return []

    print(f"  Beatmap detected: {osu_path}")

    hitobjects = parse_hitobjects(osu_path)
    print(f"  Hitobjects: {len(hitobjects)}")

    timeline = build_replay_timeline(replay)
    print(f"  Replay frames: {len(timeline)}")

    errors = []
    for t_obj, x_obj, y_obj in hitobjects:
        frame = find_closest_frame(timeline, t_obj, max_delta=80)
        if frame is None:
            continue
        _, x_r, y_r = frame

        dx = x_r - x_obj
        dy = y_r - y_obj
        dist = math.hypot(dx, dy)

        # keep only "almost hits", not big whiffs
        if dist <= include_radius:
            errors.append((dx, dy))

    print(f"  Kept errors: {len(errors)}")
    return errors


# ========= visualization =========

def plot_error_cloud(errors, output_path="aim_bias_map.png"):
    """Plot where you are hitting relative to the circle center."""
    if not errors:
        print("[i] Not enough data to draw plot.")
        return

    dxs = [e[0] for e in errors]
    dys = [e[1] for e in errors]
    dists = [math.hypot(dx, dy) for dx, dy in errors]

    # Flip Y for a more intuitive "up is up" display
    dys_plot = [-dy for dy in dys]

    plt.figure(figsize=(6, 6))

    # Hit circle outline (radius ~64 px)
    circle = plt.Circle((0, 0), 64, fill=False, linestyle="--")
    plt.gca().add_patch(circle)

    plt.scatter(dxs, dys_plot, c=dists, cmap="coolwarm", s=10, marker="+", alpha=0.7)

    plt.axhline(0, linestyle=":", linewidth=0.8)
    plt.axvline(0, linestyle=":", linewidth=0.8)

    plt.gca().set_aspect("equal", "box")
    plt.xlabel("Error X (px)  –  left < 0, right > 0")
    plt.ylabel("Error Y (px)  –  up > 0, down < 0")
    plt.title("Aim impact cloud around circle center")

    plt.colorbar(label="Distance from center (px)")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()

    print(f"[i] Aim map saved to: {output_path}")


# ========= summary & area adjustment =========

def summarize_errors(errors, area_w_mm, area_h_mm, adjust_threshold_mm=0.25):
    """
    Print global stats and recommended area adjustment.

    adjust_threshold_mm = minimum bias (in mm) before suggesting a correction.
    """
    if not errors:
        print("\n[!] No usable errors collected.")
        return

    dxs = [e[0] for e in errors]
    dys = [e[1] for e in errors]

    mean_dx = statistics.mean(dxs)
    mean_dy = statistics.mean(dys)

    mean_dx_mm = mean_dx / 512.0 * area_w_mm
    mean_dy_mm = mean_dy / 384.0 * area_h_mm

    quad_counts = {
        "top-left": 0,
        "top-right": 0,
        "bottom-left": 0,
        "bottom-right": 0,
    }

    for dx, dy in errors:
        if dx < 0 and dy < 0:
            quad_counts["top-left"] += 1
        elif dx >= 0 and dy < 0:
            quad_counts["top-right"] += 1
        elif dx < 0 and dy >= 0:
            quad_counts["bottom-left"] += 1
        else:
            quad_counts["bottom-right"] += 1

    total = len(errors)

    print("\n=== Global aim bias summary ===")
    print(f"Total samples: {total}")
    print(f"Mean bias (osu! px): dx = {mean_dx:.2f}, dy = {mean_dy:.2f}")
    print("Mean bias on your tablet area:")
    print(f"  dx = {mean_dx_mm:.3f} mm  (positive = to the right)")
    print(f"  dy = {mean_dy_mm:.3f} mm  (positive = downwards)")

    print("\nError distribution by quadrant (%):")
    for name, count in quad_counts.items():
        pct = count / total * 100.0
        print(f"  {name:12s}: {pct:5.1f}%")

    # Area adjustment suggestion
    print("\n=== Area adjustment suggestion ===")
    abs_dx_mm = abs(mean_dx_mm)
    abs_dy_mm = abs(mean_dy_mm)

    if abs_dx_mm < adjust_threshold_mm and abs_dy_mm < adjust_threshold_mm:
        print(
            f"Your average bias is below {adjust_threshold_mm:.2f} mm "
            "on both axes. No meaningful adjustment seems necessary."
        )
        return

    print("On average, you tend to aim:")
    dir_x = "right" if mean_dx > 0 else "left"
    dir_y = "down" if mean_dy > 0 else "up"
    print(f"  → {abs_dx_mm:.2f} mm too far to the {dir_x}")
    print(f"  → {abs_dy_mm:.2f} mm too far {dir_y}")

    corr_dx_mm = -mean_dx_mm
    corr_dy_mm = -mean_dy_mm
    corr_dir_x = "right" if corr_dx_mm > 0 else "left"
    corr_dir_y = "down" if corr_dy_mm > 0 else "up"

    print("\nTo compensate, you could try shifting your active area by approximately:")
    print(f"  {abs(corr_dx_mm):.2f} mm towards the {corr_dir_x}")
    print(f"  {abs(corr_dy_mm):.2f} mm towards {corr_dir_y}")
    print("Adjust this according to how your tablet driver handles offsets.")


# ========= interactive main (for CLI or .exe) =========

def interactive_main():
    print("=== osu! tablet aim bias analyzer (MD5 + auto map lookup) ===\n")

    # 1) Ask for tablet area
    while True:
        try:
            area_w_mm = float(input("Enter your tablet area WIDTH in mm (e.g. 72.9): ").strip())
            area_h_mm = float(input("Enter your tablet area HEIGHT in mm (e.g. 52): ").strip())
            break
        except ValueError:
            print("Invalid number, please try again.\n")

    # 2) Ask for Songs folder
    default_songs = r"C:\Users\user\AppData\Local\osu!\Songs"
    print(f"\nDefault Songs folder: {default_songs}")
    songs_folder = input("Press Enter to use this, or type a custom Songs path: ").strip()
    if not songs_folder:
        songs_folder = default_songs

    while not os.path.isdir(songs_folder):
        print(f"[ERROR] This folder does not exist: {songs_folder}")
        songs_folder = input("Please enter a valid Songs folder path: ").strip()

    # 3) Replays folder
    default_replays = "Replays"
    print(f"\nDefault replays folder: {default_replays}")
    replays_folder = input("Press Enter to use this, or type another folder: ").strip()
    if not replays_folder:
        replays_folder = default_replays

    if not os.path.isdir(replays_folder):
        print(f"[i] Creating replays folder: {replays_folder}")
        os.makedirs(replays_folder, exist_ok=True)

    # Ask user to drop .osr files if folder is empty
    while True:
        replay_files = [
            os.path.join(replays_folder, f)
            for f in os.listdir(replays_folder)
            if f.lower().endswith(".osr")
        ]
        if replay_files:
            break
        print(f"\n[!] No .osr files found in '{replays_folder}'.")
        input("Drop some replay files into that folder, then press Enter to continue...")

    print(f"\n[i] Found {len(replay_files)} replay(s) to analyze.")

    all_errors = []
    for rp in replay_files:
        errs = analyze_replay_with_md5(rp, songs_folder, include_radius=80.0)
        all_errors.extend(errs)

    summarize_errors(all_errors, area_w_mm, area_h_mm, adjust_threshold_mm=0.25)
    plot_error_cloud(all_errors, output_path="aim_bias_map.png")

    print("\nDone. You can now open 'aim_bias_map.png' to see your aim distribution.")


if __name__ == "__main__":
    interactive_main()
