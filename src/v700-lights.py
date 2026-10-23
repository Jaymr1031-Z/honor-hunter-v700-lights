#!/usr/bin/env python3
import argparse
import colorsys
import fcntl
import json
import math
import os
from pathlib import Path
import random
import select
import signal
import struct
import time

BASE = Path('/sys/kernel/honer_v700_lights')
BACKUP = Path('/var/lib/honer-v700-lights/original-lighting.json')
LOCK_PATH = Path('/run/lock/honer-v700-lights.lock')
DAEMON_PID_PATH = Path('/run/honer-v700-lights-daemon.pid')
DAEMON_STATE_PATH = Path('/run/honer-v700-lights-effect.json')

ZONES = {'logo': 0xA0, 'b0': 0xB0, 'd0': 0xD0}
D0_SEGMENTS = [(0, 19), (20, 35), (36, 51), (52, 69)]
D0_BOUNDARIES = {0, 20, 36, 52}
KBD_ZONES = 4

# 16 sub-blocks across the 70 Wind Valley LEDs, used for static hardware gradients.
D0_BLOCKS = [
    (0, 4), (5, 9), (10, 14), (15, 19),
    (20, 23), (24, 27), (28, 31), (32, 35),
    (36, 39), (40, 43), (44, 47), (48, 51),
    (52, 56), (57, 60), (61, 64), (65, 69),
]

STATIC_THEMES = {
    'ice-blue': {
        'label': '冰川蓝',
        'logo': (0, 170, 255),
        'kbd': [(0, 170, 255)] * 4,
        'stops': [(0, 170, 255)],
    },
    'cyber-purple': {
        'label': '赛博紫',
        'logo': (168, 85, 247),
        'kbd': [(168, 85, 247)] * 4,
        'stops': [(168, 85, 247)],
    },
    'gaming-red': {
        'label': '电竞红',
        'logo': (255, 30, 39),
        'kbd': [(255, 30, 39)] * 4,
        'stops': [(255, 30, 39)],
    },
    'aurora-green': {
        'label': '极光绿',
        'logo': (0, 255, 136),
        'kbd': [(0, 255, 136)] * 4,
        'stops': [(0, 255, 136)],
    },
    'sakura-pink': {
        'label': '樱花粉',
        'logo': (255, 77, 166),
        'kbd': [(255, 77, 166)] * 4,
        'stops': [(255, 77, 166)],
    },
    'sunset-gold': {
        'label': '流光金',
        'logo': (255, 184, 0),
        'kbd': [(255, 184, 0)] * 4,
        'stops': [(255, 184, 0)],
    },
    'ocean-cyan': {
        'label': '深海青',
        'logo': (0, 240, 255),
        'kbd': [(0, 240, 255)] * 4,
        'stops': [(0, 240, 255)],
    },
    'pure-white': {
        'label': '纯净白',
        'logo': (255, 255, 255),
        'kbd': [(255, 255, 255)] * 4,
        'stops': [(255, 255, 255)],
    },
    'gradient-rainbow': {
        'label': '霓虹彩虹渐变',
        'logo': (0, 210, 255),
        'kbd': [(255, 0, 80), (255, 200, 0), (0, 240, 130), (140, 40, 255)],
        'stops': [
            (255, 0, 64),
            (255, 120, 0),
            (255, 220, 0),
            (0, 255, 100),
            (0, 210, 255),
            (110, 50, 255),
            (230, 0, 255),
        ],
    },
    'gradient-cyberpunk': {
        'label': '赛博朋克撞色',
        'logo': (255, 0, 127),
        'kbd': [(255, 0, 127), (195, 30, 255), (90, 140, 255), (0, 240, 255)],
        'stops': [
            (255, 0, 127),
            (168, 40, 255),
            (0, 240, 255),
        ],
    },
    'gradient-fire-ice': {
        'label': '冰火两重天',
        'logo': (255, 90, 0),
        'kbd': [(255, 25, 0), (255, 140, 0), (0, 190, 255), (0, 70, 255)],
        'stops': [
            (255, 20, 0),
            (255, 140, 0),
            (0, 190, 255),
            (0, 60, 255),
        ],
    },
    'gradient-aurora': {
        'label': '极光幻境渐变',
        'logo': (0, 255, 136),
        'kbd': [(0, 255, 128), (0, 210, 220), (40, 120, 255), (150, 40, 255)],
        'stops': [
            (0, 255, 128),
            (0, 180, 255),
            (140, 40, 255),
        ],
    },
    'hunter-fps': {
        'label': '猎人竞技 (WASD 烈焰红)',
        'logo': (255, 30, 39),
        'kbd': [(255, 25, 35), (0, 170, 255), (0, 170, 255), (255, 25, 35)],
        'stops': [
            (255, 25, 35),
            (0, 170, 255),
            (0, 170, 255),
            (255, 25, 35),
        ],
    },
}

DYNAMIC_EFFECTS = {
    'key-ripple': '💧 按键波纹涟漪',
    'key-rainbow': '🎆 七彩打字烟花',
    'key-reactive': '⚡ 疾速按键充能',
    'breathe': '💨 单色呼吸灯',
    'breathe-rainbow': '🎇 七彩交替呼吸',
    'marquee': '☄️ 流光跑马灯',
    'scanner': '🛸 霹雳游侠扫描',
    'rainbow-wave': '🌊 动态彩虹波浪',
    'cyber-pulse': '🔮 赛博双色律动',
}

# Mapping of Linux input keycodes to physical keyboard horizontal position (0.0 .. 3.0)
KEYCODE_ZONE_MAP = {}
for _k in (1, 59, 60, 61, 62, 41, 2, 3, 4, 5, 15, 16, 17, 18, 19, 58, 30, 31, 32, 33, 42, 44, 45, 46, 29, 125, 56):
    KEYCODE_ZONE_MAP[_k] = 0.0
for _k in (63, 64, 65, 66, 6, 7, 8, 9, 20, 21, 22, 23, 34, 35, 36, 37, 47, 48, 49, 50):
    KEYCODE_ZONE_MAP[_k] = 1.0
KEYCODE_ZONE_MAP[57] = 1.35  # Spacebar spans center-left & center-right
for _k in (67, 68, 87, 88, 10, 11, 12, 13, 14, 24, 25, 26, 27, 43, 38, 39, 40, 28, 51, 52, 53, 54, 100, 97, 105, 103, 108, 106):
    KEYCODE_ZONE_MAP[_k] = 2.0
for _k in (69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 96, 98, 55, 102, 104, 107, 109, 110, 111):
    KEYCODE_ZONE_MAP[_k] = 3.0


def keycode_to_zone_pos(code):
    if code in KEYCODE_ZONE_MAP:
        return KEYCODE_ZONE_MAP[code]
    return float(code % KBD_ZONES)


def open_keyboard_event_fds():
    fds = []
    try:
        content = Path('/proc/bus/input/devices').read_text(errors='ignore')
        for block in content.split('\n\n'):
            if 'EV=120013' in block or 'at translated set 2 keyboard' in block.lower():
                for line in block.splitlines():
                    if line.startswith('H: Handlers='):
                        for token in line.split():
                            if token.startswith('event'):
                                dev_path = Path('/dev/input') / token
                                try:
                                    fd = os.open(dev_path, os.O_RDONLY | os.O_NONBLOCK)
                                    fds.append(fd)
                                except OSError:
                                    pass
    except OSError:
        pass
    return fds


def drain_key_events(fds):
    """Return (pressed_positions, had_any_key_activity).
    Drains all pending EV_KEY events so we know both what zones were hit and
    whether the user's fingers are currently active on the keyboard.
    """
    if not fds:
        return [], False
    event_struct = struct.Struct('llHHi')
    size = event_struct.size
    pressed_positions = []
    had_activity = False
    try:
        readable, _, _ = select.select(fds, [], [], 0.0)
    except OSError:
        return [], False
    for fd in readable:
        while True:
            try:
                buf = os.read(fd, size * 32)
                if not buf:
                    break
                for offset in range(0, len(buf) - (len(buf) % size), size):
                    _sec, _usec, ev_type, ev_code, ev_val = event_struct.unpack_from(buf, offset)
                    if ev_type == 1:  # EV_KEY (press, release, or repeat)
                        had_activity = True
                        if ev_val == 1:  # Key press down
                            pressed_positions.append(keycode_to_zone_pos(ev_code))
            except (BlockingIOError, OSError):
                break
    return pressed_positions, had_activity


def backup_path(zone):
    if zone == 'logo':
        return BACKUP
    return BACKUP.with_name('original-lighting-' + zone + '.json')


def read_request(zone, selector):
    data = bytearray(64)
    data[:4] = bytes([6, 6, ZONES[zone], selector])
    return data


def off_requests(zone):
    data = bytearray(64)
    if zone == 'logo':
        # HHBgService 1.0.61.0: 0x1400f0870 -> 0x1400f0a70.
        data[:9] = bytes([6, 5, 0xA0, 0, 0, 0, 0, 0, 1])
    elif zone == 'b0':
        # Set all 4 keyboard zones to static black (mode 0, count 1) for verified readback.
        result = []
        for selector in range(KBD_ZONES):
            packet = bytearray(64)
            packet[:9] = bytes([6, 5, 0xB0, 0, selector, selector, 0, 0, 1])
            result.append(packet)
        return result
    else:
        # HHBgService 1.0.61.0: 0x1400f0870 -> 0x1400f04d0.
        result = []
        for start, end in D0_SEGMENTS:
            packet = bytearray(64)
            packet[:9] = bytes([6, 5, 0xD0, 0, start, end, 1, 0x2C, 1])
            result.append(packet)
        return result
    return [data]


def parse_hex_color(value, brightness=100):
    cleaned = value.strip().lstrip('#')
    if len(cleaned) != 6:
        raise ValueError('Color must be a 6-digit hex value (RRGGBB)')
    raw = bytes.fromhex(cleaned)
    scale = max(0, min(100, int(brightness))) / 100.0
    return tuple(max(0, min(255, int(round(c * scale)))) for c in raw)


def scale_rgb(rgb, factor):
    factor = max(0.0, min(1.0, float(factor)))
    return tuple(max(0, min(255, int(round(c * factor)))) for c in rgb)


def add_rgb(c1, c2):
    return tuple(max(0, min(255, int(round(a + b)))) for a, b in zip(c1, c2))


def lerp_rgb(c1, c2, t):
    t = max(0.0, min(1.0, float(t)))
    return tuple(
        max(0, min(255, int(round(a + (b - a) * t))))
        for a, b in zip(c1, c2)
    )


def color_diff(c1, c2):
    if c1 is None or c2 is None:
        return 999
    return max(abs(a - b) for a, b in zip(c1, c2))


def multi_stop_gradient(stops, count, brightness=100):
    if not stops:
        raise ValueError('At least one color stop is required')
    scale = max(0, min(100, int(brightness))) / 100.0
    scaled_stops = [scale_rgb(s, scale) for s in stops]
    if len(scaled_stops) == 1 or count <= 1:
        return [scaled_stops[0]] * count
    result = []
    segments = len(scaled_stops) - 1
    for i in range(count):
        pos = (i / (count - 1)) * segments
        idx = min(int(pos), segments - 1)
        frac = pos - idx
        result.append(lerp_rgb(scaled_stops[idx], scaled_stops[idx + 1], frac))
    return result


def write_packet(zone, start, end, rgb):
    data = bytearray(64)
    r, g, b = (max(0, min(255, int(c))) for c in rgb)
    data[:12] = bytes([6, 5, ZONES[zone], 0, start, end, 0, 0, 1, r, g, b])
    return data


def color_requests(zone, rgb):
    if zone == 'logo':
        return [write_packet('logo', 0, 0, rgb)]
    if zone == 'b0':
        return [write_packet('b0', sel, sel, rgb) for sel in range(KBD_ZONES)]
    if zone == 'd0':
        return [write_packet('d0', start, end, rgb) for start, end in D0_SEGMENTS]
    raise ValueError('Unsupported zone for color write: ' + str(zone))


def kbd_zone_requests(zone_colors):
    if len(zone_colors) != KBD_ZONES:
        raise ValueError('Expected exactly 4 colors for keyboard zones')
    return [write_packet('b0', sel, sel, rgb) for sel, rgb in enumerate(zone_colors)]


def d0_segment_requests(seg_colors):
    if len(seg_colors) != len(D0_SEGMENTS):
        raise ValueError('Expected 4 segment colors for d0')
    return [
        write_packet('d0', start, end, rgb)
        for (start, end), rgb in zip(D0_SEGMENTS, seg_colors)
    ]


def d0_block_requests(block_colors):
    if len(block_colors) != len(D0_BLOCKS):
        raise ValueError('Expected exactly 16 block colors for d0')
    merged = []
    for (start, end), rgb in zip(D0_BLOCKS, block_colors):
        rgb_tuple = tuple(max(0, min(255, int(c))) for c in rgb)
        if merged and start not in D0_BOUNDARIES and merged[-1][2] == rgb_tuple and merged[-1][1] + 1 == start:
            merged[-1] = (merged[-1][0], end, rgb_tuple)
        else:
            merged.append((start, end, rgb_tuple))
    return [write_packet('d0', start, end, rgb) for start, end, rgb in merged]


def theme_requests(theme_name, brightness=100, include_kbd=True):
    if theme_name not in STATIC_THEMES:
        raise ValueError('Unknown theme: ' + str(theme_name))
    theme = STATIC_THEMES[theme_name]
    scale = max(0, min(100, int(brightness))) / 100.0
    logo_rgb = scale_rgb(theme['logo'], scale)
    packets = color_requests('logo', logo_rgb)
    if include_kbd and 'kbd' in theme:
        kbd_colors = [scale_rgb(c, scale) for c in theme['kbd']]
        packets.extend(kbd_zone_requests(kbd_colors))
    stops = theme['stops']
    if len(stops) == 1:
        packets.extend(color_requests('d0', scale_rgb(stops[0], scale)))
    else:
        block_colors = multi_stop_gradient(stops, len(D0_BLOCKS), brightness=brightness)
        packets.extend(d0_block_requests(block_colors))
    return packets


def invoke(data):
    if len(data) != 64:
        raise ValueError('Request must contain exactly 64 bytes')
    req_hex = data.hex() + '\n'
    for attempt in range(6):
        if attempt:
            time.sleep(0.015)
        try:
            (BASE / 'request').write_text(req_hex)
            reply = bytes.fromhex((BASE / 'response').read_text())
        except OSError:
            continue
        if len(reply) == 256 and reply[0] == 0:
            if data[1] != 6 or (reply[1] == data[2] and reply[3] == data[3]):
                return reply
    raise RuntimeError('Firmware did not return a successful 256-byte reply')


def write_fast(data):
    """Fast write-only path for animation frames (kernel already verifies response[0] == 0)."""
    (BASE / 'request').write_text(data.hex() + '\n')


def capture(selected):
    snapshots = []
    for zone in ZONES:
        if zone != selected:
            continue
        for selector in range({'logo': 1, 'b0': 4, 'd0': 70}[zone]):
            reply = invoke(read_request(zone, selector))
            if reply[1] != ZONES[zone] or reply[3] != selector:
                raise RuntimeError('Firmware returned a different lamp selector')
            # Only static single-color states have a verified inverse here.
            if reply[2] != 0 or reply[6] != 1:
                raise RuntimeError('Original effect is not supported by safe restore')
            snapshots.append({'zone': zone, 'selector': selector, 'reply': reply.hex()})
    return snapshots


def restore_request(item):
    reply = bytes.fromhex(item['reply'])
    data = bytearray(64)
    data[:9] = bytes([6, 5, ZONES[item['zone']], reply[2], item['selector'],
                     item['selector'], reply[4], reply[5], reply[6]])
    data[9:12] = reply[7:10]
    return data


def restore_requests(snapshots):
    result = []
    for item in snapshots:
        data = restore_request(item)
        # Preserve the original service's segment boundaries on D0.
        boundary = item['zone'] != 'd0' or item['selector'] in [0, 20, 36, 52]
        if result and not boundary:
            previous = result[-1]
            if (previous[:4] == data[:4] and previous[6:] == data[6:]
                    and previous[5] + 1 == data[4]):
                previous[5] = data[5]
                continue
        result.append(data)
    return result


def validated_backup(zone):
    snapshots = json.loads(backup_path(zone).read_text())
    expected = {'logo': 1, 'b0': 4, 'd0': 70}[zone]
    if len(snapshots) != expected:
        raise RuntimeError('Backup is incomplete')
    for selector, item in enumerate(snapshots):
        reply = bytes.fromhex(item['reply'])
        if (item['zone'] != zone or item['selector'] != selector
                or len(reply) != 256 or reply[:4] != bytes([0, ZONES[zone], 0, selector])
                or reply[6] != 1):
            raise RuntimeError('Backup is not a verified static lamp state')
    return snapshots


def apply_packets_locked(packets):
    with open(LOCK_PATH, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for pkt in packets:
            invoke(pkt)


def hsv_to_rgb_int(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))


def run_effect_loop(effect_name, base_rgb=(0, 170, 255), speed='normal', brightness=100, target='all'):
    """EC-friendly dynamic lighting loop with Zero-Lag Typing Guard.

    Because the built-in keyboard (i8042) and ACPI WMI lighting share the same
    Embedded Controller (EC0), sending WMI packets while the user's fingers are
    actively typing causes EC bus contention. This loop monitors keyboard activity
    and yields 100% of the EC bus during rapid keystrokes (<110ms between key events),
    then renders smooth 4-zone/4-segment animations during inter-word pauses.
    """
    speed_mult = {'slow': 0.65, 'normal': 1.0, 'fast': 1.55}.get(speed, 1.0)
    bright_scale = max(10, min(100, int(brightness))) / 100.0
    primary = scale_rgb(base_rgb, bright_scale)
    if not any(primary):
        primary = scale_rgb((0, 170, 255), bright_scale)

    running = True

    def handle_stop(_signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    # Always monitor keyboard events so ALL effects yield the EC bus while typing!
    kbd_fds = open_keyboard_event_fds()
    is_key_effect = effect_name in ('key-ripple', 'key-rainbow', 'key-reactive')

    n_segs = len(D0_SEGMENTS)  # 4 hardware segments matching the 4 keyboard zones
    start_time = time.monotonic()
    last_logo = None
    last_kbd = [None] * KBD_ZONES
    last_segs = [None] * n_segs

    ripples = []
    rainbow_hue = 0.0
    energy_level = 0.0
    last_key_activity_time = 0.0

    # Quiet window required after the last key press/release before WMI writes run:
    # 110ms guarantees zero WMI calls while typing fast syllables ("jiuhui"),
    # while still triggering within 0.11s the moment a key or word finishes!
    TYPING_QUIET_WINDOW = 0.115

    try:
        while running:
            now = time.monotonic()
            new_keys, had_activity = drain_key_events(kbd_fds)
            if had_activity:
                last_key_activity_time = now

            if is_key_effect and new_keys:
                for pos in new_keys:
                    if effect_name == 'key-rainbow':
                        rainbow_hue = (rainbow_hue + 0.19 + random.uniform(0.0, 0.07)) % 1.0
                        r_color = hsv_to_rgb_int(rainbow_hue, 0.95, bright_scale)
                    else:
                        r_color = primary
                    # Coalesce ripples that hit the same zone within 120ms
                    if ripples and abs(ripples[-1]['pos'] - pos) < 0.6 and (now - ripples[-1]['t0']) < 0.12:
                        ripples[-1]['t0'] = now
                        ripples[-1]['color'] = r_color
                    else:
                        ripples.append({'pos': pos, 't0': now, 'color': r_color})
                    energy_level = min(1.0, energy_level + 0.25)

            # If the user is actively typing right now, DO NOT touch the EC bus!
            time_since_key = now - last_key_activity_time
            if time_since_key < TYPING_QUIET_WINDOW:
                wait_rem = max(0.015, TYPING_QUIET_WINDOW - time_since_key)
                try:
                    select.select(kbd_fds, [], [], wait_rem)
                except OSError:
                    time.sleep(wait_rem)
                continue

            # Prune expired ripples (measured from when they started animating or birth)
            max_age = 0.85 / speed_mult
            ripples = [r for r in ripples if (now - r['t0']) <= max_age][-6:]
            energy_level = max(0.0, energy_level - 0.06 * speed_mult)

            elapsed = now - start_time
            t = elapsed * speed_mult

            if effect_name in ('key-ripple', 'key-rainbow'):
                base_c = scale_rgb(primary, 0.08)
                kbd_c = [base_c] * KBD_ZONES
                segs_c = [base_c] * n_segs
                logo_c = base_c

                wave_speed = 4.2 * speed_mult
                wave_width = 1.05

                for rip in ripples:
                    # Effective ripple time starts after the typing burst finishes
                    dt = max(0.0, now - max(rip['t0'], last_key_activity_time))
                    radius = dt * wave_speed
                    fade = max(0.0, 1.0 - (dt / (0.65 / speed_mult))) ** 1.3
                    rc = rip['color']

                    for z in range(KBD_ZONES):
                        dist = abs(abs(z - rip['pos']) - radius)
                        if dist < wave_width:
                            strength = ((1.0 - dist / wave_width) ** 1.5) * fade
                            col = add_rgb(kbd_c[z], scale_rgb(rc, strength))
                            kbd_c[z] = col
                            segs_c[z] = add_rgb(segs_c[z], scale_rgb(rc, strength))

                    if dt < 0.28:
                        logo_strength = (1.0 - dt / 0.28) * fade
                        logo_c = add_rgb(logo_c, scale_rgb(rc, logo_strength))

                sleep_sec = 0.075 if ripples else 0.25

            elif effect_name == 'key-reactive':
                idle_c = scale_rgb(primary, 0.06)
                kbd_c = [idle_c] * KBD_ZONES
                for rip in ripples:
                    dt = max(0.0, now - max(rip['t0'], last_key_activity_time))
                    fade = max(0.0, 1.0 - dt / (0.50 / speed_mult)) ** 1.6
                    for z in range(KBD_ZONES):
                        proximity = max(0.0, 1.0 - abs(z - rip['pos']) * 0.7)
                        kbd_c[z] = add_rgb(kbd_c[z], scale_rgb(rip['color'], fade * proximity))

                lit_segs = int(round(energy_level * n_segs))
                segs_c = [primary if i < lit_segs else idle_c for i in range(n_segs)]
                logo_c = scale_rgb(primary, max(0.1, energy_level))
                sleep_sec = 0.08 if (ripples or energy_level > 0.01) else 0.25

            elif effect_name == 'breathe':
                wave = 0.06 + 0.94 * (0.5 * (1.0 - math.cos(t * 2.2)))
                c = scale_rgb(primary, wave)
                logo_c = c
                kbd_c = [c] * KBD_ZONES
                segs_c = [c] * n_segs
                sleep_sec = 0.085

            elif effect_name == 'breathe-rainbow':
                cycle = t * 0.38
                hue = (int(cycle) * 0.19 + (cycle % 1.0) * 0.08) % 1.0
                wave = 0.06 + 0.94 * (math.sin((cycle % 1.0) * math.pi) ** 1.6)
                c = hsv_to_rgb_int(hue, 0.95, wave * bright_scale)
                logo_c = c
                kbd_c = [c] * KBD_ZONES
                segs_c = [c] * n_segs
                sleep_sec = 0.085

            elif effect_name == 'marquee':
                pos = (t * 2.6) % n_segs
                kbd_c = []
                for z in range(n_segs):
                    dist = (pos - z) % n_segs
                    w = max(0.08, 1.0 - dist * 0.42) if dist < 2.2 else 0.08
                    kbd_c.append(scale_rgb(primary, w))
                segs_c = list(kbd_c)
                logo_c = kbd_c[1]
                sleep_sec = 0.085

            elif effect_name == 'scanner':
                span = (n_segs - 1) * 2
                pos_raw = (t * 3.2) % span
                head = pos_raw if pos_raw <= (n_segs - 1) else span - pos_raw
                kbd_c = []
                for z in range(n_segs):
                    dist = abs(z - head)
                    w = max(0.06, 1.0 - dist * 0.55)
                    kbd_c.append(scale_rgb(primary, w))
                segs_c = list(kbd_c)
                logo_c = scale_rgb(primary, 0.35 + 0.65 * abs(math.sin(t * 2.6)))
                sleep_sec = 0.085

            elif effect_name == 'rainbow-wave':
                kbd_c = []
                for z in range(n_segs):
                    hue = (z / float(n_segs) - t * 0.28) % 1.0
                    kbd_c.append(hsv_to_rgb_int(hue, 0.95, bright_scale))
                segs_c = list(kbd_c)
                logo_c = kbd_c[1]
                sleep_sec = 0.095

            elif effect_name == 'cyber-pulse':
                c_pink = scale_rgb((255, 0, 127), bright_scale)
                c_cyan = scale_rgb((0, 240, 255), bright_scale)
                phase = (math.sin(t * 2.8) + 1.0) * 0.5
                logo_c = lerp_rgb(c_pink, c_cyan, phase)
                kbd_c = []
                for z in range(n_segs):
                    local_phase = (math.sin(t * 2.8 + z * 0.8) + 1.0) * 0.5
                    kbd_c.append(lerp_rgb(c_pink, c_cyan, local_phase))
                segs_c = list(kbd_c)
                sleep_sec = 0.09

            else:
                raise ValueError('Unsupported effect: ' + str(effect_name))

            # Only queue packets whose RGB changed significantly (>= 10 steps)
            queued = []
            if target in ('all', 'keyboard'):
                for sel in range(KBD_ZONES):
                    if color_diff(kbd_c[sel], last_kbd[sel]) >= 10:
                        queued.append(('b0', sel, kbd_c[sel], write_packet('b0', sel, sel, kbd_c[sel])))

            if target in ('all', 'valley'):
                for seg_idx, (start, end) in enumerate(D0_SEGMENTS):
                    if color_diff(segs_c[seg_idx], last_segs[seg_idx]) >= 10:
                        queued.append(('d0', seg_idx, segs_c[seg_idx], write_packet('d0', start, end, segs_c[seg_idx])))

            if target in ('all', 'logo') and color_diff(logo_c, last_logo) >= 10:
                queued.append(('logo', 0, logo_c, write_packet('logo', 0, 0, logo_c)))

            # Send packets one by one with a 16ms inter-packet breathing gap,
            # and abort immediately if the user presses any key!
            aborted_by_typing = False
            for idx, (z_type, z_idx, col_val, pkt) in enumerate(queued):
                if not running:
                    break
                if kbd_fds:
                    try:
                        r_ready, _, _ = select.select(kbd_fds, [], [], 0.0 if idx == 0 else 0.016)
                        if r_ready:
                            aborted_by_typing = True
                            break
                    except OSError:
                        pass
                elif idx > 0:
                    time.sleep(0.016)

                try:
                    with open(LOCK_PATH, 'w') as lock:
                        fcntl.flock(lock, fcntl.LOCK_EX)
                        write_fast(pkt)
                    if z_type == 'b0':
                        last_kbd[z_idx] = col_val
                    elif z_type == 'd0':
                        last_segs[z_idx] = col_val
                    elif z_type == 'logo':
                        last_logo = col_val
                except Exception:
                    break

            if aborted_by_typing:
                continue

            if kbd_fds:
                try:
                    select.select(kbd_fds, [], [], sleep_sec)
                except OSError:
                    time.sleep(sleep_sec)
            else:
                slept = 0.0
                while running and slept < sleep_sec:
                    time.sleep(min(0.02, sleep_sec - slept))
                    slept += 0.02
    finally:
        for fd in kbd_fds:
            try:
                os.close(fd)
            except OSError:
                pass


def run(args):
    if args.action == 'dry-run':
        for data in off_requests(args.zone):
            print(args.zone, data.hex())
        return
    if os.geteuid() != 0:
        raise PermissionError('Run through sudo')
    with open(LOCK_PATH, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        backup = backup_path(args.zone)
        if args.action == 'backup':
            if backup.exists():
                raise FileExistsError('Backup already exists; refusing to overwrite')
            snapshots = capture(args.zone)
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as stream:
                json.dump(snapshots, stream, indent=2)
            print('Backed up', len(snapshots), 'lamp states')
        elif args.action == 'status':
            for item in capture(args.zone):
                print(item['zone'], item['selector'], item['reply'][:24])
        elif args.action == 'off':
            if not backup.exists():
                raise FileNotFoundError('Back up original lamp states first')
            snapshots = validated_backup(args.zone)
            try:
                for data in off_requests(args.zone):
                    invoke(data)
                if any(bytes.fromhex(item['reply'])[7:10] != bytes(3)
                       for item in capture(args.zone)):
                    raise RuntimeError('Lamp colors did not read back as black')
            except Exception:
                for data in restore_requests(snapshots):
                    invoke(data)
                raise
            print(args.zone, 'off command accepted')
        elif args.action == 'restore':
            snapshots = validated_backup(args.zone)
            for data in restore_requests(snapshots):
                invoke(data)
            print(args.zone, 'restored')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['dry-run', 'backup', 'status', 'off', 'restore'])
    parser.add_argument('--zone', choices=list(ZONES), required=True)
    args = parser.parse_args()
    run(args)
