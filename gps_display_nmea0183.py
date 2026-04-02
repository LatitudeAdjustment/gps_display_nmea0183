import serial
import serial.tools.list_ports
import sys
import os
import signal
import curses
import math
import argparse
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

builtins_open = open   # preserve before any method named 'open' can shadow it


# ── NMEA parser ───────────────────────────────────────────────────────────────

def parse_nmea(line):
    line = line.strip()
    if not line.startswith("$"):
        raise ValueError(f"No leading $: {line!r}")
    if "*" not in line:
        raise ValueError(f"No checksum: {line!r}")
    body, checksum_str = line[1:].rsplit("*", 1)
    checksum_str = checksum_str[:2].upper()
    computed = 0
    for ch in body:
        computed ^= ord(ch)
    parts = body.split(",")
    if len(parts[0]) < 5:
        raise ValueError(f"Sentence ID too short: {parts[0]!r}")
    return {
        "talker":   parts[0][:2],
        "sentence": parts[0][2:5],
        "fields":   parts[1:],
        "checksum": checksum_str,
        "valid":    f"{computed:02X}" == checksum_str,
    }


# ── coordinate helpers ────────────────────────────────────────────────────────

def parse_lat(value, direction):
    if not value:
        return None
    d = float(value[:2]) + float(value[2:]) / 60
    return -d if direction == "S" else d

def parse_lon(value, direction):
    if not value:
        return None
    d = float(value[:3]) + float(value[3:]) / 60
    return -d if direction == "W" else d

def fmt_lat(v):
    if v is None: return "---"
    deg = int(abs(v)); mins = (abs(v) - deg) * 60
    return f"{deg:3d}° {mins:07.4f}' {'N' if v >= 0 else 'S'}"

def fmt_lon(v):
    if v is None: return "---"
    deg = int(abs(v)); mins = (abs(v) - deg) * 60
    return f"{deg:3d}° {mins:07.4f}' {'E' if v >= 0 else 'W'}"

def fmt_time(t):
    if not t or len(t) < 6: return "--:--:-- UTC"
    return f"{t[0:2]}:{t[2:4]}:{t[4:6]} UTC"

def fmt_date(d):
    if not d or len(d) < 6: return "--/--/----"
    return f"{d[0:2]}/{d[2:4]}/20{d[4:6]}"

def norm_prn(p):
    try:
        return str(int(p))
    except (ValueError, TypeError):
        return p


# ── GPS state ─────────────────────────────────────────────────────────────────

@dataclass
class GPSState:
    utc_time:     str             = ""
    utc_date:     str             = ""
    latitude:     Optional[float] = None
    longitude:    Optional[float] = None
    altitude:     Optional[float] = None
    alt_units:    str             = "M"
    fix_quality:  int             = 0
    fix_type:     str             = ""
    status:       str             = ""
    speed_knots:  Optional[float] = None
    speed_kmh:    Optional[float] = None
    course:       Optional[float] = None
    sats_used:    int             = 0
    sats_in_view: int             = 0
    hdop:         Optional[float] = None
    vdop:         Optional[float] = None
    pdop:         Optional[float] = None
    satellites:   dict            = field(default_factory=dict)
    active_prns:  set             = field(default_factory=set)
    last_sentence: str            = ""
    error_count:  int             = 0


# ── sentence decoders ─────────────────────────────────────────────────────────

def decode_gga(s, f):
    if len(f) < 13: return
    s.utc_time    = f[0]
    s.latitude    = parse_lat(f[1], f[2])
    s.longitude   = parse_lon(f[3], f[4])
    s.fix_quality = int(f[5])   if f[5] else 0
    s.sats_used   = int(f[6])   if f[6] else 0
    s.hdop        = float(f[7]) if f[7] else None
    s.altitude    = float(f[8]) if f[8] else None
    s.alt_units   = f[9] or "M"

def decode_rmc(s, f):
    if len(f) < 9: return
    s.utc_time    = f[0]; s.status = f[1]
    s.latitude    = parse_lat(f[2], f[3])
    s.longitude   = parse_lon(f[4], f[5])
    s.speed_knots = float(f[6]) if f[6] else None
    s.course      = float(f[7]) if f[7] else None
    s.utc_date    = f[8]

def decode_gsa(s, f):
    if len(f) < 17: return
    s.fix_type    = {"1": "None", "2": "2D", "3": "3D"}.get(f[1], "")
    s.active_prns = {norm_prn(p) for p in f[2:14] if p}
    s.pdop        = float(f[14]) if f[14] else None
    s.hdop        = float(f[15]) if f[15] else None
    s.vdop        = float(f[16]) if f[16] else None

def decode_gsv(s, f):
    if len(f) < 3: return
    s.sats_in_view = int(f[2]) if f[2] else 0
    if f[1] == "1":
        s.satellites.clear()
    i = 3
    while i + 3 < len(f):
        prn = norm_prn(f[i])
        if prn:
            s.satellites[prn] = {
                "elev": int(f[i+1]) if f[i+1] else 0,
                "azim": int(f[i+2]) if f[i+2] else 0,
                "snr":  int(f[i+3]) if f[i+3] else 0,
            }
        i += 4

def decode_vtg(s, f):
    if len(f) < 7: return
    s.course      = float(f[0]) if f[0] else None
    s.speed_knots = float(f[4]) if f[4] else None
    s.speed_kmh   = float(f[6]) if f[6] else None

def decode_zda(s, f):
    if len(f) < 4: return
    s.utc_time = f[0]
    if f[1] and f[2] and f[3]:
        s.utc_date = f"{f[1].zfill(2)}{f[2].zfill(2)}{f[3][2:]}"

def decode_gll(s, f):
    if len(f) < 4: return
    s.latitude  = parse_lat(f[0], f[1])
    s.longitude = parse_lon(f[2], f[3])
    if len(f) > 4: s.utc_time = f[4]

DECODERS = {
    "GGA": decode_gga, "RMC": decode_rmc, "GSA": decode_gsa,
    "GSV": decode_gsv, "VTG": decode_vtg, "ZDA": decode_zda,
    "GLL": decode_gll,
}

FIX_QUALITY = {
    0: "Invalid", 1: "GPS", 2: "DGPS", 3: "PPS",
    4: "RTK", 5: "Float RTK", 6: "Estimated",
}

# Colour to use for each sentence type in the log
SENTENCE_COLORS = {
    "GGA": 2,   # green
    "RMC": 2,
    "GSA": 3,   # yellow
    "GSV": 3,
    "VTG": 5,   # magenta
    "GLL": 5,
    "ZDA": 6,   # cyan
}


# ── sky plot ──────────────────────────────────────────────────────────────────

def draw_sky_plot(put, state, color_pairs, sr, sc, h, w):
    if h < 7 or w < 18:
        return

    cx = sc + w // 2
    cy = sr + h // 2
    ry = h // 2 - 1
    rx = min(w // 2 - 3, ry * 2)

    BOLD = curses.A_BOLD
    DIM  = curses.A_DIM

    for elev in [0, 30, 60]:
        r = (90 - elev) / 90
        steps = max(16, int(2 * math.pi * max(rx * r, ry * r)))
        for i in range(steps):
            rad = 2 * math.pi * i / steps
            px = int(round(cx + r * rx * math.sin(rad)))
            py = int(round(cy - r * ry * math.cos(rad)))
            if sr <= py < sr + h and sc <= px < sc + w:
                put(py, px, "·", DIM)

    put(cy, cx, "+", DIM)
    put(sr,         cx,         "N", BOLD)
    put(sr + h - 1, cx,         "S", BOLD)
    put(cy,         sc + w - 1, "E", BOLD)
    put(cy,         sc,         "W", BOLD)

    for elev, label in [(0, " 0°"), (30, "30°"), (60, "60°")]:
        r = (90 - elev) / 90
        lx = cx + int(round(r * rx)) + 1
        if sr <= cy < sr + h and sc <= lx < sc + w - 3:
            put(cy, lx, label, DIM)

    for prn, sat in state.satellites.items():
        elev = sat["elev"]
        azim = sat["azim"]
        snr  = sat["snr"]
        r    = (90 - elev) / 90
        rad  = math.radians(azim)
        px   = int(round(cx + r * rx * math.sin(rad)))
        py   = int(round(cy - r * ry * math.cos(rad)))

        if not (sr <= py < sr + h and sc <= px < sc + w):
            continue

        active = prn in state.active_prns
        if active:
            attr = color_pairs["good"] | BOLD
            dot  = "●"
        elif snr > 0:
            attr = color_pairs["ok"]
            dot  = "○"
        else:
            attr = DIM
            dot  = "·"

        put(py, px, dot, attr)
        lx = px + 1 if px + 1 + len(prn) <= sc + w else px - len(prn)
        if sr <= py < sr + h and sc <= lx < sc + w:
            put(py, lx, prn, attr)


# ── SNR helpers ───────────────────────────────────────────────────────────────

def fix_quality_score(state):
    """Return (label, bar_width 0-20, color_key) representing overall fix quality."""
    if state.fix_quality == 0:
        return "No Fix", 0, "weak"

    scores = []

    # Satellite count (0-5 pts)
    scores.append(min(state.sats_used / 8 * 5, 5))

    # Average SNR of active satellites (0-5 pts)
    active_snrs = [
        sat["snr"] for prn, sat in state.satellites.items()
        if prn in state.active_prns and sat["snr"] > 0
    ]
    if active_snrs:
        scores.append(min((sum(active_snrs) / len(active_snrs)) / 45 * 5, 5))
    else:
        scores.append(0)

    # HDOP (0-5 pts, lower is better)
    if state.hdop is not None:
        scores.append(max(0, 5 - (state.hdop - 1) * 1.25))
    else:
        scores.append(2.5)

    # Fix type (0-5 pts)
    scores.append({"3D": 5, "2D": 2, "None": 0}.get(state.fix_type, 2.5))

    total = sum(scores)          # 0–20
    bar   = int(round(total))

    if   total >= 16: label, color = "Excellent", "good"
    elif total >= 11: label, color = "Good",      "good"
    elif total >= 7:  label, color = "Fair",      "ok"
    else:             label, color = "Poor",      "weak"

    return label, bar, color


def snr_bar(snr, width=10):
    if not snr:
        return "─" * width
    filled = min(int(snr / 50 * width), width)
    return "█" * filled + "░" * (width - filled)

def snr_color(snr, pairs):
    if snr >= 40: return pairs["good"]
    if snr >= 25: return pairs["ok"]
    return pairs["weak"]


# ── file logging state ────────────────────────────────────────────────────────

@dataclass
class LogState:
    active:   bool   = False
    path:     str    = ""
    count:    int    = 0
    error:    str    = ""
    handle:   object = None

    def start(self, path):
        self.path  = path
        self.error = ""
        try:
            self.handle = builtins_open(path, "a")
            self.active = True
        except OSError as e:
            self.error  = str(e)
            self.active = False

    def write(self, line):
        if self.active and self.handle:
            self.handle.write(line + "\n")
            self.handle.flush()
            self.count += 1

    def stop(self):
        if self.handle:
            self.handle.close()
            self.handle = None
        self.active = False

    def toggle(self, default_path):
        if self.active:
            self.stop()
        else:
            self.start(self.path or default_path)


# ── main draw ─────────────────────────────────────────────────────────────────

LOG_LINES = 15

def draw(stdscr, state, nmea_log, log_state, color_pairs):
    stdscr.erase()
    H, W = stdscr.getmaxyx()

    def put(r, c, text, attr=0):
        if 0 <= r < H and 0 <= c < W:
            try:
                stdscr.addstr(r, c, text[:W-c], attr)
            except curses.error:
                pass

    BOLD = curses.A_BOLD
    DIM  = curses.A_DIM
    HDR  = color_pairs["header"] | BOLD

    # Top section always gets at least 22 rows so the satellite table
    # and sky plot are never squeezed out.  On small terminals the log
    # shows fewer than 15 lines rather than crushing the main display.
    MIN_TOP  = 25
    LOG_TOP  = max(H - LOG_LINES - 1, MIN_TOP)

    # ── title ─────────────────────────────────────────────────────────────────
    title = " BU-353S4 GPS Monitor "
    put(0, max(0, (W - len(title)) // 2), title, HDR)
    put(1, 0, "═" * W, HDR)

    # ── log status row ────────────────────────────────────────────────────────
    if log_state.active:
        log_attr = color_pairs["good"] | curses.A_BOLD
        log_icon = "● REC"
        log_info = f"{log_state.path}  {log_state.count} lines"
    elif log_state.error:
        log_attr = color_pairs["weak"] | curses.A_BOLD
        log_icon = "✗ ERR"
        log_info = log_state.error
    else:
        log_attr = curses.A_DIM
        log_icon = "○ OFF"
        log_info = log_state.path if log_state.path else "(no file set)"
    put(2, 0,  "Log:", curses.A_BOLD)
    put(2, 6,  log_icon, log_attr)
    put(2, 12, log_info, log_attr)
    put(2, W - 38, "[p] port  [l] toggle logging", curses.A_DIM)
    put(3, 0, "─" * W, curses.A_DIM)

    INFO_TOP = 4
    INFO_W   = 42

    # ── left info panel ───────────────────────────────────────────────────────
    row = INFO_TOP

    put(row, 0,  "Time:",  BOLD); put(row, 7,  fmt_time(state.utc_time))
    put(row, 22, "Date:",  BOLD); put(row, 28, fmt_date(state.utc_date))
    row += 1

    fix_str  = FIX_QUALITY.get(state.fix_quality, "Unknown")
    fix_attr = color_pairs["good"] if state.fix_quality >= 1 else color_pairs["weak"]
    put(row, 0,  "Fix:",   BOLD); put(row, 6,  f"{fix_str} {state.fix_type}", fix_attr | BOLD)
    put(row, 22, "Sats:",  BOLD); put(row, 28, f"{state.sats_used} used / {state.sats_in_view} in view")
    row += 1

    put(row, 0,  "Lat:",   BOLD); put(row, 6,  fmt_lat(state.latitude))
    alt = f"{state.altitude:.1f} {state.alt_units}" if state.altitude is not None else "---"
    put(row, 28, "Alt:",   BOLD); put(row, 33, alt)
    row += 1

    put(row, 0,  "Lon:",   BOLD); put(row, 6,  fmt_lon(state.longitude))
    row += 1

    spd = "---"
    if state.speed_knots is not None:
        spd = f"{state.speed_knots:.1f} kn"
        if state.speed_kmh is not None:
            spd += f"  ({state.speed_kmh:.1f} km/h)"
    put(row, 0,  "Speed:", BOLD); put(row, 7,  spd)
    put(row, 28, "Crs:",   BOLD)
    put(row, 33, f"{state.course:.1f}°" if state.course is not None else "---")
    row += 1

    put(row, 0,  "HDOP:", BOLD); put(row, 6,  f"{state.hdop:.1f}" if state.hdop else "---")
    put(row, 13, "VDOP:", BOLD); put(row, 19, f"{state.vdop:.1f}" if state.vdop else "---")
    put(row, 26, "PDOP:", BOLD); put(row, 32, f"{state.pdop:.1f}" if state.pdop else "---")
    row += 1

    # ── overall fix quality ───────────────────────────────────────────────────
    qlabel, qbar, qcolor = fix_quality_score(state)
    qattr  = color_pairs[qcolor] | BOLD
    filled = "█" * qbar
    empty  = "░" * (20 - qbar)
    put(row, 0, "Quality:", BOLD)
    put(row, 9, f"{filled}{empty}", qattr)
    put(row, 30, f"{qlabel}", qattr)
    row += 1

    # ── satellite SNR table (fills remaining left-column space) ───────────────
    put(row, 0, "─" * INFO_W, DIM); row += 1
    put(row, 0, f" {'PRN':>3} {'El':>3}  {'Az':>3}  {'SNR':>3}    Signal", BOLD); row += 1
    put(row, 0, "─" * INFO_W, DIM); row += 1

    for prn, sat in sorted(state.satellites.items(), key=lambda x: -x[1]["snr"]):
        if row >= LOG_TOP:
            break
        snr     = sat["snr"]
        bar     = snr_bar(snr, width=10)
        snr_str = f"{snr:2d}" if snr else "--"
        active  = prn in state.active_prns
        attr    = snr_color(snr, color_pairs)
        marker  = "●" if active else " "
        put(row, 0, f" {prn:>3} {sat['elev']:>3}° {sat['azim']:>3}° {snr_str:>3} {marker} ")
        put(row, 22, bar, attr | BOLD)
        put(row, 33, f" {snr_str}dB", attr)
        row += 1

    # ── sky plot (right column, full top-area height) ─────────────────────────
    SKY_COL = INFO_W + 1
    sky_w   = W - SKY_COL
    sky_h   = LOG_TOP - INFO_TOP

    if sky_w >= 18 and sky_h >= 7:
        for r in range(INFO_TOP, LOG_TOP):
            put(r, INFO_W, "│", DIM)
        draw_sky_plot(put, state, color_pairs, INFO_TOP, SKY_COL, sky_h, sky_w)

    # ── NMEA log separator ────────────────────────────────────────────────────
    label = " NMEA sentences "
    sep   = "─" * ((W - len(label)) // 2) + label + "─" * ((W - len(label) + 1) // 2)
    put(LOG_TOP, 0, sep[:W], DIM)

    # ── NMEA log lines ────────────────────────────────────────────────────────
    for i, (line, valid, sentence_type) in enumerate(nmea_log):
        r = LOG_TOP + 1 + i
        if r >= H:
            break
        if not valid:
            attr = color_pairs["weak"]
        else:
            pair_id = SENTENCE_COLORS.get(sentence_type, 0)
            attr = curses.color_pair(pair_id) if pair_id else curses.A_NORMAL
        put(r, 0, line[:W], attr)

    stdscr.refresh()


# ── port picker ───────────────────────────────────────────────────────────────

def pick_port(stdscr):
    """Interactive port selection screen. Returns chosen port string or None to quit."""
    curses.curs_set(0)
    # Use pairs 7/8 so we don't overwrite the main display's color pairs 1-6
    curses.init_pair(7, curses.COLOR_CYAN,  -1)
    curses.init_pair(8, curses.COLOR_BLACK, curses.COLOR_CYAN)   # highlight

    sel = 0

    while True:
        ports = sorted(serial.tools.list_ports.comports(), key=lambda p: p.device)

        stdscr.erase()
        H, W = stdscr.getmaxyx()

        title = " Select Serial Port "
        stdscr.addstr(0, max(0, (W - len(title)) // 2), title,
                      curses.color_pair(7) | curses.A_BOLD)
        stdscr.addstr(1, 0, "─" * W, curses.A_DIM)

        if not ports:
            stdscr.addstr(3, 2, "No serial ports found. Plug in your GPS and press [r] to refresh.",
                          curses.color_pair(7))
        else:
            sel = min(sel, len(ports) - 1)
            for i, p in enumerate(ports):
                attr = curses.color_pair(8) | curses.A_BOLD if i == sel else curses.A_NORMAL
                desc = f"  {p.device:<30} {p.description}"
                stdscr.addstr(3 + i, 0, desc[:W], attr)

        stdscr.addstr(H - 1, 0,
                      " ↑↓ select   Enter confirm   r refresh   q quit "[:W],
                      curses.A_DIM)
        stdscr.refresh()

        key = stdscr.getch()
        if key in (ord("q"), ord("Q")):
            return None
        if key in (ord("r"), ord("R")):
            continue
        if key == curses.KEY_UP and sel > 0:
            sel -= 1
        if key == curses.KEY_DOWN and ports and sel < len(ports) - 1:
            sel += 1
        if key in (curses.KEY_ENTER, 10, 13) and ports:
            return ports[sel].device


# ── main ──────────────────────────────────────────────────────────────────────

def main(stdscr):
    parser = argparse.ArgumentParser(description="BU-353S4 GPS display")
    parser.add_argument("port", nargs="?", default=None,
                        help="Serial port (optional — picker shown if omitted)")
    parser.add_argument("--log", "-l", metavar="FILE",
                        help="Log file path (logging starts immediately if given)")
    args = parser.parse_args()

    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()

    # Show port picker if no port given on command line
    if args.port is None:
        chosen = pick_port(stdscr)
        if chosen is None:
            return
        args.port = chosen

    stdscr.nodelay(True)

    curses.init_pair(1, curses.COLOR_CYAN,    -1)   # header
    curses.init_pair(2, curses.COLOR_GREEN,   -1)   # GGA / RMC
    curses.init_pair(3, curses.COLOR_YELLOW,  -1)   # GSA / GSV
    curses.init_pair(4, curses.COLOR_RED,     -1)   # error / weak
    curses.init_pair(5, curses.COLOR_MAGENTA, -1)   # VTG / GLL
    curses.init_pair(6, curses.COLOR_CYAN,    -1)   # ZDA

    color_pairs = {
        "header": curses.color_pair(1),
        "good":   curses.color_pair(2),
        "ok":     curses.color_pair(3),
        "weak":   curses.color_pair(4),
    }

    state     = GPSState()
    nmea_log  = deque(maxlen=LOG_LINES)
    log_state = LogState()

    if args.log:
        log_state.start(args.log)
    else:
        # Pre-fill a default path so the user can see what will be created
        log_state.path = datetime.now().strftime("gps_%Y%m%d_%H%M%S.nmea")

    def open_port(port):
        return serial.Serial(port, baudrate=4800, timeout=0)

    # ser_holder lets the signal handler reach the current serial object
    ser_holder = [None]

    def handle_sigtstp(signum, frame):
        """Ctrl-Z: disconnect, restore terminal, then suspend."""
        if ser_holder[0]:
            ser_holder[0].close()
            ser_holder[0] = None
        curses.endwin()
        signal.signal(signal.SIGTSTP, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGTSTP)   # actually suspend

    def handle_sigcont(signum, frame):
        """fg resume: reinitialize curses and re-arm the Ctrl-Z handler."""
        curses.doupdate()
        signal.signal(signal.SIGTSTP, handle_sigtstp)

    signal.signal(signal.SIGTSTP, handle_sigtstp)
    signal.signal(signal.SIGCONT,  handle_sigcont)

    def process_line(line, state, nmea_log, log_state):
        try:
            parsed = parse_nmea(line)
            valid  = parsed["valid"]
            stype  = parsed["sentence"] if valid else ""
            if valid:
                decoder = DECODERS.get(stype)
                if decoder:
                    decoder(state, parsed["fields"])
                state.last_sentence = stype
            else:
                state.error_count += 1
            nmea_log.append((line, valid, stype))
            log_state.write(line)
        except (ValueError, IndexError):
            nmea_log.append((line, False, ""))
            log_state.write(line)
            state.error_count += 1

    buf = b""
    ser_holder[0] = None

    while True:
        ser = ser_holder[0]

        # ── key input ─────────────────────────────────────────────────────────
        ch = stdscr.getch()
        if ch in (ord("q"), ord("Q")):
            break
        if ch in (ord("l"), ord("L")):
            if not log_state.path:
                log_state.path = datetime.now().strftime("gps_%Y%m%d_%H%M%S.nmea")
            log_state.toggle(log_state.path)
        if ch in (ord("p"), ord("P")):
            if ser:
                ser.close()
                ser_holder[0] = None
                ser = None
            chosen = pick_port(stdscr)
            if chosen:
                args.port = chosen
            stdscr.nodelay(True)
            draw(stdscr, state, nmea_log, log_state, color_pairs)

        # ── connect / reconnect ───────────────────────────────────────────────
        if ser_holder[0] is None:
            try:
                ser_holder[0] = open_port(args.port)
                buf = b""
                nmea_log.append((f"[connected to {args.port}]", False, ""))
                draw(stdscr, state, nmea_log, log_state, color_pairs)
            except OSError:
                nmea_log.append((f"[waiting for {args.port}...]", False, ""))
                draw(stdscr, state, nmea_log, log_state, color_pairs)
                time.sleep(1)
                continue

        ser = ser_holder[0]

        # ── non-blocking serial read ───────────────────────────────────────────
        try:
            waiting = ser.in_waiting
            if waiting:
                buf += ser.read(waiting)
            else:
                time.sleep(0.02)
        except OSError:
            ser.close()
            ser_holder[0] = None
            buf = b""
            nmea_log.append(("[device disconnected — waiting for reconnect]", False, ""))
            draw(stdscr, state, nmea_log, log_state, color_pairs)
            time.sleep(1)
            continue

        # ── process any complete lines in the buffer ───────────────────────────
        updated = False
        while b"\n" in buf:
            raw, buf = buf.split(b"\n", 1)
            line = raw.replace(b"\x00", b"").decode("ascii", errors="replace").strip()
            if line:
                process_line(line, state, nmea_log, log_state)
                updated = True

        if updated or ch != -1:
            draw(stdscr, state, nmea_log, log_state, color_pairs)

    if ser_holder[0]:
        ser_holder[0].close()
    log_state.stop()


if __name__ == "__main__":
    curses.wrapper(main)
