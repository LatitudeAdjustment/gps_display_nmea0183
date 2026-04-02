# README.md

GPS display application in Python created with Claude Code.

## Running the Program

```bash
python gps_display_nmea0183.py /dev/cu.usbserial-1110
```

## Options

[p] Allows selection of input port.
[l] toggles logging

Displays the following:

## Fix Data (upper left)

- Time and date (UTC)
- Fix: GPS 3D or GPS 2D; Number of satellites used and in view
- Latitude, Longitude, Altitude
- Speed, Course
- HDOP, VDOP, PDOP (Dilution of Precision)
These are Dilution of Precision values — they measure how much the geometry of
   the satellites in view amplifies GPS positioning errors. Lower is better.

  ┌───────┬───────────────┬─────────────────────────────────────────────────┐
  │ Value │     Name      │                    Measures                     │
  ├───────┼───────────────┼─────────────────────────────────────────────────┤
  │ HDOP  │ Horizontal    │ Accuracy in the horizontal plane                │
  │       │ DOP           │ (latitude/longitude)                            │
  ├───────┼───────────────┼─────────────────────────────────────────────────┤
  │ VDOP  │ Vertical DOP  │ Accuracy in the vertical axis (altitude)        │
  ├───────┼───────────────┼─────────────────────────────────────────────────┤
  │ PDOP  │ Position DOP  │ Overall 3D position accuracy (combines H and V) │
  └───────┴───────────────┴─────────────────────────────────────────────────┘

  How to read them:

  ┌───────┬────────────────────────────────┐
  │ Value │             Rating             │
  ├───────┼────────────────────────────────┤
  │ 1     │ Ideal — best possible geometry │
  ├───────┼────────────────────────────────┤
  │ 1–2   │ Excellent                      │
  ├───────┼────────────────────────────────┤
  │ 2–5   │ Good                           │
  ├───────┼────────────────────────────────┤
  │ 5–10  │ Moderate — usable              │
  ├───────┼────────────────────────────────┤
  │ 10–20 │ Fair — use with caution        │
  ├───────┼────────────────────────────────┤
  │ >20   │ Poor — results unreliable      │
  └───────┴────────────────────────────────┘

  In practice, HDOP is the most useful for navigation since GPS altitude is
  always less accurate than horizontal position. VDOP is typically worse
  (higher) than HDOP because all satellites are above you — there's nothing
  below the horizon to improve vertical geometry.

  PDOP is related by: PDOP² = HDOP² + VDOP²

- Quality: overall quality of fix

## Bar Chart (lower left)

Lower-left display of satellite location and signal strength.

PRN — Pseudo-Random Noise code number

  It's simply the ID number of the satellite. Each GPS satellite broadcasts a
  unique digital code that the receiver uses to identify it. The number is
  permanently assigned to that satellite for its lifetime.

For the BU-353S4 (GPS only) you'll see numbers 1–32.

El — Elevation
  The angle of the satellite above the horizon, in degrees.

- 0° = on the horizon
- 90° = directly overhead (zenith)
- Low elevation satellites (<15°) are often blocked by buildings/trees and
  have weaker signals

Az — Azimuth
  The compass direction to the satellite, in degrees clockwise from north.

- 0° = North
- 90° = East
- 180° = South
- 270° = West

SNR — Signal to Noise Ratio
  The strength of the satellite signal in dB-Hz. Higher is better.

- 0 = no signal
- 1–25 = weak
- 26–35 = moderate
- 36–45 = good
- 46+ = excellent

Signal — Bar graph
  A visual representation of the SNR value, scaled to 50 dB-Hz maximum.

- Color coded: green (≥40), yellow (≥25), red (<25)
- prefix means the satellite is actively used in the fix
- prefix means the satellite is in view but not used

## Skyplot (right)

Satellite constellation, looking down, north up

## NMEA sentences (bottom)
