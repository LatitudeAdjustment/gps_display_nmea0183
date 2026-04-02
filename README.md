# README.md

GPS display application in Python created with Claude Code.

Reads NMEA 0183 data from GlobalSat BU-353S4 via USB serial port.

## References

<https://www.globalsat.com.tw/en/a4-10593/BU-353S4.html>

<https://en.wikipedia.org/wiki/NMEA_0183>

<https://actisense.com/wp-content/uploads/2020/01/NMEA-0183-Information-sheet-issue-4-1-1.pdf>

<https://tronico.fi/OH6NT/docs/NMEA0183.pdf>

Additional information at ~/Documents/BU-353S4.

## Running the Program

```bash
python gps_display_nmea0183.py /dev/cu.usbserial-1110
```

### Python Environment Issue

A Python environment is required to run the program or an error will occur.

```bash
$ python gps_display_nmea0183.py /dev/cu.usbserial-1110
  File "gps_display_nmea0183.py", line 18
SyntaxError: Non-ASCII character '\xe2' in file gps_display_nmea0183.py on line 18, but no encoding declared; see http://python.org/dev/peps/pep-0263/ for details
```

### Set Up Environment

A virtual environment for Python is required.
Set up the virtual environment as follows (done previously):

```bash
$ python3 -m venv ~/serial-venv
$ source ~/serial-venv/bin/activate
$ pip install pyserial
Requirement already satisfied: pyserial in /Users/username/serial-venv/lib/python3.14/site-packages (3.5)

[notice] A new release of pip is available: 25.3 -> 26.0.1
[notice] To update, run: pip install --upgrade pip
```

### Define Environment

After setting up the environment, define it as follows prior to running the
application:

```bash
source ~/serial-venv/bin/activate
python gps_display_nmea0183.py /dev/cu.usbserial-1110
```

### Exit the Program

Enter ctrl-z to exit.

## Options

### Input Port

[p] Allows selection of input port.

For example:

```text
/dev/cu.Bluetooth-Incoming-Port n/a
/dev/cu.SoundcoreSpaceA40      n/a
/dev/cu.debug-console          n/a
/dev/cu.usbserial-1110         USB-Serial Controller D
```

### Logging

[l] toggles logging

Data is written to a file with the name gps_YYYYMMDD_hhmmss.nmea which
represents the start time for the application.

## Fix Data (upper left)

Displays the following:

- Time and date (UTC)

  | Sentence | Field        | Format                        | Example          |
  |----------|--------------|-------------------------------|------------------|
  | ZDA      | Time (UTC)   | HHMMSS.ss                     | 123519.00        |
  | ZDA      | Day          | DD                            | 13               |
  | ZDA      | Month        | MM                            | 06               |
  | ZDA      | Year         | YYYY                          | 1994             |
  | ZDA      | TZ Hours     | Local timezone offset hours   | -05              |
  | ZDA      | TZ Minutes   | Local timezone offset minutes | 00               |
  |*GGA      | Time (UTC)   | HHMMSS.ss                     | 123519.00        |
  |*RMC      | Time (UTC)   | HHMMSS.ss                     | 123519.00        |
  |*RMC      | Date         | DDMMYY                        | 130694           |
  | GLL      | Time (UTC)   | HHMMSS.ss                     | 123519.00        |

  Note: ZDA is the most complete time sentence, providing full date with
  four-digit year and timezone offset. RMC provides date but with only a
  two-digit year. GGA and GLL provide time only with no date. All times are UTC
  — convert to local time using the timezone offset from ZDA.

- Fix: GPS 3D or GPS 2D; Number of satellites used and in view

  From the GSA sentence, field 1 is the fix mode and field 2 is the fix type:

  Fix type (GSA field 2):

  | Value | Fix Type |
  |-------|----------|
  | 1     | No fix   |
  | 2     | 2D — latitude/longitude only (minimum 3 satellites) |
  | 3     | 3D — latitude, longitude and altitude (minimum 4 satellites) |

  Fix quality (GGA field 6):
  
  | Value | Fix Quality  | Description                          |
  |-------|--------------|--------------------------------------|
  | 0     | Invalid      | No fix                               |
  | 1     | GPS          | Standard fix                         |
  | 2     | DGPS         | Differential GPS, corrected fix      |
  | 3     | PPS          | Military precise positioning         |
  | 4     | RTK          | Real-time kinematic, centimeter accuracy |
  | 5     | Float RTK    | RTK with floating ambiguity          |
  | 6     | Estimated    | Dead reckoning                       |
  | 7     | Manual       | Manual input                         |
  | 8     | Simulation   | Simulation mode                      |

- Latitude, Longitude, Altitude

  | Sentence | Field        | Format                        | Example        |
  |----------|--------------|-------------------------------|----------------|
  | GGA      | Latitude     | DDMM.MMMM, N/S                | 4807.038, N    |
  | GGA      | Longitude    | DDDMM.MMMM, E/W               | 01131.000, E   |
  | GGA      | Altitude     | Meters above mean sea level   | 545.4 M        |
  | GGA      | Geoid Sep    | Difference between ellipsoid and mean sea level | 46.9 M |
  | RMC      | Latitude     | DDMM.MMMM, N/S                | 4807.038, N    |
  | RMC      | Longitude    | DDDMM.MMMM, E/W               | 01131.000, E   |
  | GLL      | Latitude     | DDMM.MMMM, N/S                | 4807.038, N    |
  | GLL      | Longitude    | DDDMM.MMMM, E/W               | 01131.000, E   |

  Note: Only GGA provides altitude. RMC and GLL provide position only. The raw
  format DDMM.MMMM means degrees followed by decimal minutes — not decimal
  degrees. For example 4807.038 is 48° 07.038' which converts to 48.1173°
  decimal degrees.

- Speed, Course

  | Sentence | Field          | Units                    | Example  |
  |----------|----------------|--------------------------|----------|
  | VTG      | Course (true)  | Degrees clockwise from true north    | 231.8 T |
  | VTG      | Course (magnetic) | Degrees clockwise from magnetic north | 229.3 M |
  | VTG      | Speed          | Knots                    | 173.8 N  |
  | VTG      | Speed          | Kilometers per hour      | 322.0 K  |
  | RMC      | Course         | Degrees clockwise from true north    | 231.8 |
  | RMC      | Speed          | Knots                    | 173.8    |

  Note: VTG is the most complete source for speed and course as it provides both
   true and magnetic course plus speed in two units. RMC provides speed in knots
   and true course only. Magnetic variation (the difference between true and
  magnetic north) varies by location and changes slowly over time.

- HDOP, VDOP, PDOP (Dilution of Precision)
These are Dilution of Precision values — they measure how much the geometry of
   the satellites in view amplifies GPS positioning errors. Lower is better.

  | Value | Name | Measures |
  |-------|------|----------|
  | HDOP  | Horizontal Dilution of Precision | Accuracy in the horizontal plane (latitude/longitude) |
  | VDOP  | Vertical Dilution of Precision   | Accuracy in the vertical axis (altitude)              |
  | PDOP  | Position Dilution of Precision   | Overall 3D position accuracy (combines HDOP and VDOP) |

  How to read them:

  | Value | Rating   |
  |-------|----------|
  | 1     | Ideal    |
  | 1–2   | Excellent|
  | 2–5   | Good     |
  | 5–10  | Moderate |
  | 10–20 | Fair     |
  | >20   | Poor     |

  In practice, HDOP is the most useful for navigation since GPS altitude is
  always less accurate than horizontal position. VDOP is typically worse
  (higher) than HDOP because all satellites are above you — there's nothing
  below the horizon to improve vertical geometry.

  PDOP is related by: PDOP² = HDOP² + VDOP²

- Quality: overall quality of fix

  | Score | Rating    | Satellites Used | Avg SNR     | HDOP      | Fix Type |
  |-------|-----------|-----------------|-------------|-----------|----------|
  | 16–20 | Excellent | 8+              | ≥45 dB-Hz   | ≤1.0      | 3D       |
  | 11–15 | Good      | 6–7             | ≥35 dB-Hz   | 1.0–2.0   | 3D       |
  | 7–10  | Fair      | 4–5             | ≥25 dB-Hz   | 2.0–5.0   | 2D or 3D |
  | 1–6   | Poor      | <4              | <25 dB-Hz   | >5.0      | 2D       |
  | 0     | No Fix    | 0               | —           | —         | None     |

  Note: The score is a composite of four equally weighted factors — satellite
  count, average SNR of active satellites, HDOP, and fix type — each
  contributing up to 5 points for a maximum of 20.

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

Displays satellite constellation, looking down, north up.
Each satellite has a number which corresponds to the bargraph.

## NMEA sentences (bottom)

Displays each NMEA 0183 sentence as it is received.

```text
$GPGGA,180115.000,4104.4978,N,07326.7688,W,1,07,1.2,6.1,M,-34.3,M,,0000*6A
$GPGSA,M,3,06,19,17,22,11,03,12,,,,,,2.2,1.2,1.8*3C
$GPGSV,3,1,12,06,74,284,23,19,74,018,30,17,55,085,23,22,42,168,37*74
$GPGSV,3,2,12,11,33,246,17,03,26,044,30,12,21,315,22,50,00,000,*7B
$GPGSV,3,3,12,25,65,254,,28,51,172,,24,08,271,,09,04,118,*78
$GPRMC,180115.000,A,4104.4978,N,07326.7688,W,0.00,0.66,020426,,,A*70
$GPGGA,180116.000,4104.4978,N,07326.7688,W,1,07,1.2,6.1,M,-34.3,M,,0000*69
$GPGSA,M,3,06,19,17,22,11,03,12,,,,,,2.2,1.2,1.8*3C
$GPRMC,180116.000,A,4104.4978,N,07326.7688,W,0.00,0.66,020426,,,A*73
$GPGGA,180117.000,4104.4978,N,07326.7688,W,1,07,1.2,6.1,M,-34.3,M,,0000*68
$GPGSA,M,3,06,19,17,22,11,03,12,,,,,,2.2,1.2,1.8*3C
$GPRMC,180117.000,A,4104.4978,N,07326.7688,W,0.00,0.66,020426,,,A*72
$GPGGA,180118.000,4104.4978,N,07326.7688,W,1,07,1.2,6.1,M,-34.3,M,,0000*67
$GPGSA,M,3,06,19,17,22,11,03,12,,,,,,2.2,1.2,1.8*3C
$GPRMC,180118.000,A,4104.4978,N,07326.7688,W,0.00,0.66,020426,,,A*7D
$GPGGA,180119.000,4104.4978,N,07326.7688,W,1,07,1.2,6.1,M,-34.3,M,,0000*66
$GPGSA,M,3,06,19,17,22,11,03,12,,,,,,2.2,1.2,1.8*3C
$GPRMC,180119.000,A,4104.4978,N,07326.7688,W,0.00,0.66,020426,,,A*7C
$GPGGA,180120.000,4104.4978,N,07326.7688,W,1,07,1.2,6.1,M,-34.3,M,,0000*6C
$GPGSA,M,3,06,19,17,22,11,03,12,,,,,,2.2,1.2,1.8*3C
$GPGSV,3,1,12,06,74,284,24,19,74,018,30,17,55,085,25,22,42,168,38*7A
$GPGSV,3,2,12,11,33,246,17,03,26,044,30,12,21,315,23,50,00,000,*7A
```
