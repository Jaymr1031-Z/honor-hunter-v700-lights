#!/usr/bin/python3
"""GNOME application for Honor Hunter V700 RGB lighting (LOGO, 4-Zone Keyboard, 70-LED Wind Valley)."""
import colorsys
import json
import math
import subprocess
import sys
import threading
import time

import gi
gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')
from gi.repository import Gdk, GLib, Gtk

PRESET_COLORS = [
    ('冰川蓝', '#00aaff'),
    ('赛博紫', '#a855f7'),
    ('电竞红', '#ff1e27'),
    ('极光绿', '#00ff88'),
    ('樱花粉', '#ff4da6'),
    ('流光金', '#ffb800'),
    ('深海青', '#00f0ff'),
    ('纯净白', '#ffffff'),
]

GRADIENT_THEMES = [
    ('gradient-rainbow', '🌈 霓虹彩虹渐变', '键盘 4 区 + 风谷 16 段全光谱 · 零后台占用'),
    ('gradient-cyberpunk', '⚡ 赛博朋克撞色', '霓虹洋红 → 电光紫 → 赛博青'),
    ('gradient-fire-ice', '🔥 冰火两重天', '左侧烈焰红橙 ↔ 右侧冰川深蓝'),
    ('gradient-aurora', '🌌 极光幻境渐变', '极光翠绿 → 深海蓝 → 星云紫'),
    ('hunter-fps', '🎮 猎人竞技 FPS', 'WASD 左区与右区烈焰红 + 中区冰川蓝'),
]

DYNAMIC_EFFECTS = [
    ('key-ripple', '💧 按键波纹涟漪', '敲击按键从对应分区向键盘和风谷灯扩散波纹'),
    ('key-rainbow', '🎆 七彩打字烟花', '每次按键绽放不同色相的彩虹扩散波纹'),
    ('key-reactive', '⚡ 疾速按键充能', '按键分区瞬间高亮余晖 + 风谷灯连击能量条'),
    ('breathe', '💨 单色呼吸灯', '全机身同步余弦平滑呼吸起伏'),
    ('breathe-rainbow', '🎇 七彩交替呼吸', '全光谱色相循环呼吸切换'),
    ('marquee', '☄️ 流光跑马灯', '键盘 4 区与风谷灯 16 段同步流星追逐'),
    ('scanner', '🛸 霹雳游侠扫描', 'KITT 机甲风左右回弹扫描光束'),
    ('rainbow-wave', '🌊 动态彩虹波浪', '键盘与风谷灯同步流动全彩波浪'),
    ('cyber-pulse', '🔮 赛博双色律动', '霓虹洋红与赛博青相位交错律动'),
]

KBD_ZONE_LABELS = ['左区 (WASD)', '中左 (主键)', '中右 (回车)', '右区 (数字)']


def hex_to_rgb(hex_str):
    cleaned = hex_str.strip().lstrip('#')
    if len(cleaned) != 6:
        return (0, 170, 255)
    return tuple(bytes.fromhex(cleaned))


def rgb_to_hex(rgb):
    r, g, b = (max(0, min(255, int(round(c)))) for c in rgb)
    return f'#{r:02x}{g:02x}{b:02x}'


def scale_rgb(rgb, factor):
    factor = max(0.0, min(1.0, float(factor)))
    return tuple(max(0, min(255, int(round(c * factor)))) for c in rgb)


def lerp_rgb(c1, c2, t):
    t = max(0.0, min(1.0, float(t)))
    return tuple(a + (b - a) * t for a, b in zip(c1, c2))


class LightControl(Gtk.Application):
    def __init__(self, self_check=False):
        super().__init__(application_id='local.honer.LightControl')
        self.self_check = self_check
        self.window = None
        self.buttons = []
        self.states = {}
        self.busy = False
        self.selected_hex = '#00aaff'
        self.kbd_zone_hexes = ['#00aaff', '#00ff00', '#ffff00', '#ff2424']
        self.kbd_color_btns = []
        self.target_zone = 'all'
        self.effect_speed = 'normal'
        self.brightness = 100
        self.logo_preview = None
        self.kbd_bars = []
        self.valley_bars = []
        self.dynamic_provider = None
        self.active_effect_label = None
        self.color_btn = None
        self.active_effect = None
        self.anim_timer_id = None
        self.anim_start = time.monotonic()

    def make_action_button(self, text, cmd_args, suggested=False, destructive=False, css_class=None):
        button = Gtk.Button(label=text)
        if suggested:
            button.add_css_class('suggested-action')
        if destructive:
            button.add_css_class('destructive-action')
        if css_class:
            button.add_css_class(css_class)
        button.connect('clicked', lambda _btn: self.perform(cmd_args))
        self.buttons.append(button)
        return button

    def build_visualizer(self):
        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        frame.add_css_class('visualizer-card')

        top_row = Gtk.Box(spacing=12)
        title = Gtk.Label(label='全机身实时灯效预览 · 荣耀猎人 V700', xalign=0, hexpand=True)
        title.add_css_class('heading')
        top_row.append(title)

        self.active_effect_label = Gtk.Label(label='静态硬件模式', xalign=1)
        self.active_effect_label.add_css_class('effect-badge')
        top_row.append(self.active_effect_label)
        frame.append(top_row)

        leds_row = Gtk.Box(spacing=18)

        # LOGO orb preview
        logo_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        logo_box.set_valign(Gtk.Align.CENTER)
        self.logo_preview = Gtk.Box()
        self.logo_preview.set_size_request(52, 52)
        self.logo_preview.set_halign(Gtk.Align.CENTER)
        self.logo_preview.add_css_class('logo-orb')
        logo_caption = Gtk.Label(label='A 面 LOGO')
        logo_caption.add_css_class('caption')
        logo_box.append(self.logo_preview)
        logo_box.append(logo_caption)
        leds_row.append(logo_box)

        right_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, hexpand=True)

        # 4-Zone Keyboard preview bar
        kbd_outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        kbd_box = Gtk.Box(spacing=8, homogeneous=True, hexpand=True)
        self.kbd_bars = []
        for idx, z_label in enumerate(KBD_ZONE_LABELS):
            z_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            z_box.set_size_request(60, 28)
            z_box.add_css_class('kbd-bar')
            z_box.add_css_class(f'kbd-bar-{idx}')
            lbl = Gtk.Label(label=z_label)
            lbl.add_css_class('kbd-zone-text')
            lbl.set_valign(Gtk.Align.CENTER)
            lbl.set_vexpand(True)
            z_box.append(lbl)
            self.kbd_bars.append(z_box)
            kbd_box.append(z_box)
        kbd_outer.append(kbd_box)
        right_col.append(kbd_outer)

        # 16-segment Wind Valley strip preview
        strip_outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        strip_box = Gtk.Box(spacing=4, homogeneous=True, hexpand=True)
        self.valley_bars = []
        for idx in range(16):
            bar = Gtk.Box()
            bar.set_size_request(14, 20)
            bar.add_css_class('valley-bar')
            bar.add_css_class(f'valley-bar-{idx}')
            self.valley_bars.append(bar)
            strip_box.append(bar)
        strip_caption = Gtk.Label(label='上方：四分区 RGB 键盘 · 下方：机身风谷 70 灯珠 16 分段灯带', xalign=0)
        strip_caption.add_css_class('caption')
        strip_outer.append(strip_box)
        strip_outer.append(strip_caption)
        right_col.append(strip_outer)

        leds_row.append(right_col)
        frame.append(leds_row)
        return frame

    def card(self, title, subtitle, zone, on_cmd, off_cmd, on_label='默认灯效'):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class('lamp-card')
        heading = Gtk.Label(label=title, xalign=0)
        heading.add_css_class('heading')
        card.append(heading)
        detail = Gtk.Label(label=subtitle, xalign=0)
        detail.add_css_class('dim-label')
        card.append(detail)
        state = Gtk.Label(label='未读取状态', xalign=0)
        self.states[zone] = state
        card.append(state)
        buttons = Gtk.Box(spacing=8, homogeneous=True)
        buttons.append(self.make_action_button(on_label, [on_cmd], suggested=True))
        buttons.append(self.make_action_button('关闭', [off_cmd]))
        card.append(buttons)
        return card

    def build_color_section(self):
        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        section.add_css_class('lamp-card')

        header_row = Gtk.Box(spacing=10)
        title = Gtk.Label(label='🎨 潮流换色与键盘四分区独立调色', xalign=0, hexpand=True)
        title.add_css_class('heading')
        header_row.append(title)

        target_box = Gtk.Box(spacing=4)
        for key, label in [
            ('all', '全部灯区'),
            ('keyboard', '仅键盘'),
            ('valley', '仅风谷灯'),
            ('logo', '仅 LOGO'),
        ]:
            btn = Gtk.ToggleButton(label=label)
            btn.set_active(key == self.target_zone)
            btn.connect('toggled', self.on_target_toggled, key)
            if key != 'all':
                btn.set_group(self._first_target_btn)
            else:
                self._first_target_btn = btn
            target_box.append(btn)
        header_row.append(target_box)
        section.append(header_row)

        grid = Gtk.Grid(column_spacing=8, row_spacing=8, column_homogeneous=True)
        for idx, (name, hex_val) in enumerate(PRESET_COLORS):
            swatch_btn = Gtk.Button()
            swatch_btn.add_css_class('swatch-btn')
            row_box = Gtk.Box(spacing=8)
            row_box.set_halign(Gtk.Align.CENTER)
            dot = Gtk.Box()
            dot.set_size_request(14, 14)
            dot.set_valign(Gtk.Align.CENTER)
            dot.add_css_class(f'swatch-dot-{idx}')
            lbl = Gtk.Label(label=name)
            row_box.append(dot)
            row_box.append(lbl)
            swatch_btn.set_child(row_box)
            swatch_btn.connect('clicked', lambda _b, h=hex_val: self.apply_selected_color(h))
            self.buttons.append(swatch_btn)
            grid.attach(swatch_btn, idx % 4, idx // 4, 1, 1)
        section.append(grid)

        custom_row = Gtk.Box(spacing=12)
        rgba = Gdk.RGBA()
        rgba.parse(self.selected_hex)
        if hasattr(Gtk, 'ColorDialog') and hasattr(Gtk, 'ColorDialogButton'):
            dialog = Gtk.ColorDialog(with_alpha=False)
            self.color_btn = Gtk.ColorDialogButton(dialog=dialog, rgba=rgba)
            self.color_btn.connect('notify::rgba', self.on_custom_rgba_changed)
        else:
            self.color_btn = Gtk.ColorButton()
            self.color_btn.set_rgba(rgba)
            self.color_btn.connect('color-set', self.on_custom_rgba_changed)
        custom_row.append(self.color_btn)

        apply_custom = Gtk.Button(label='应用单色')
        apply_custom.add_css_class('suggested-action')
        apply_custom.connect('clicked', lambda _b: self.apply_selected_color(self.selected_hex))
        self.buttons.append(apply_custom)
        custom_row.append(apply_custom)

        bright_lbl = Gtk.Label(label='亮度', xalign=1)
        bright_lbl.add_css_class('dim-label')
        custom_row.append(bright_lbl)

        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 20, 100, 5)
        scale.set_value(100)
        scale.set_draw_value(True)
        scale.set_value_pos(Gtk.PositionType.RIGHT)
        scale.set_hexpand(True)
        scale.connect('value-changed', self.on_brightness_changed)
        custom_row.append(scale)
        section.append(custom_row)

        # 4-Zone Keyboard independent color pickers
        kbd_custom_row = Gtk.Box(spacing=10)
        kbd_lbl = Gtk.Label(label='⌨️ 键盘四区撞色：', xalign=0)
        kbd_lbl.add_css_class('dim-label')
        kbd_custom_row.append(kbd_lbl)

        self.kbd_color_btns = []
        for z_idx, z_name in enumerate(['左区', '中左', '中右', '右区']):
            z_rgba = Gdk.RGBA()
            z_rgba.parse(self.kbd_zone_hexes[z_idx])
            if hasattr(Gtk, 'ColorDialog') and hasattr(Gtk, 'ColorDialogButton'):
                z_dialog = Gtk.ColorDialog(with_alpha=False)
                c_btn = Gtk.ColorDialogButton(dialog=z_dialog, rgba=z_rgba)
                c_btn.connect('notify::rgba', self.on_kbd_zone_rgba_changed, z_idx)
            else:
                c_btn = Gtk.ColorButton()
                c_btn.set_rgba(z_rgba)
                c_btn.connect('color-set', self.on_kbd_zone_rgba_changed, z_idx)
            self.kbd_color_btns.append(c_btn)
            pair = Gtk.Box(spacing=4)
            pair.append(Gtk.Label(label=z_name))
            pair.append(c_btn)
            kbd_custom_row.append(pair)

        apply_kbd_4 = Gtk.Button(label='应用键盘四色')
        apply_kbd_4.connect('clicked', lambda _b: self.apply_kbd_zones())
        self.buttons.append(apply_kbd_4)
        kbd_custom_row.append(apply_kbd_4)

        section.append(kbd_custom_row)
        return section

    def build_gradient_section(self):
        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        section.add_css_class('lamp-card')

        title = Gtk.Label(label='🌈 硬件级全机渐变与电竞主题 (写入固件保持 · 零后台占用)', xalign=0)
        title.add_css_class('heading')
        section.append(title)

        grid = Gtk.Grid(column_spacing=10, row_spacing=10, column_homogeneous=True)
        for idx, (theme_id, name, desc) in enumerate(GRADIENT_THEMES):
            btn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            t_lbl = Gtk.Label(label=name, xalign=0)
            t_lbl.add_css_class('heading')
            d_lbl = Gtk.Label(label=desc, xalign=0)
            d_lbl.add_css_class('caption')
            d_lbl.add_css_class('dim-label')
            btn_box.append(t_lbl)
            btn_box.append(d_lbl)

            btn = Gtk.Button(child=btn_box)
            btn.add_css_class('effect-tile')
            btn.connect(
                'clicked',
                lambda _b, tid=theme_id: self.perform(
                    ['theme', '--name', tid, '--brightness', str(self.brightness)]
                ),
            )
            self.buttons.append(btn)
            grid.attach(btn, idx % 2, idx // 2, 1, 1)
        section.append(grid)
        return section

    def build_dynamic_section(self):
        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        section.add_css_class('lamp-card')

        header_row = Gtk.Box(spacing=10)
        title = Gtk.Label(label='🚀 动态灯效与按键涟漪引擎 (支持打字实时波纹反馈)', xalign=0, hexpand=True)
        title.add_css_class('heading')
        header_row.append(title)

        speed_box = Gtk.Box(spacing=4)
        for key, label in [('slow', '慢速'), ('normal', '标准'), ('fast', '极速')]:
            btn = Gtk.ToggleButton(label=label)
            btn.set_active(key == self.effect_speed)
            btn.connect('toggled', self.on_speed_toggled, key)
            if key != 'slow':
                btn.set_group(self._first_speed_btn)
            else:
                self._first_speed_btn = btn
            speed_box.append(btn)
        header_row.append(speed_box)

        stop_btn = self.make_action_button('⏹ 停止动效', ['stop-effect'])
        header_row.append(stop_btn)
        section.append(header_row)

        grid = Gtk.Grid(column_spacing=10, row_spacing=10, column_homogeneous=True)
        for idx, (eff_id, name, desc) in enumerate(DYNAMIC_EFFECTS):
            btn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            t_lbl = Gtk.Label(label=name, xalign=0)
            t_lbl.add_css_class('heading')
            d_lbl = Gtk.Label(label=desc, xalign=0)
            d_lbl.add_css_class('caption')
            d_lbl.add_css_class('dim-label')
            btn_box.append(t_lbl)
            btn_box.append(d_lbl)

            btn = Gtk.Button(child=btn_box)
            btn.add_css_class('effect-tile')
            btn.connect('clicked', lambda _b, eid=eff_id: self.start_effect(eid))
            self.buttons.append(btn)
            grid.attach(btn, idx % 3, idx // 3, 1, 1)
        section.append(grid)
        return section

    def on_target_toggled(self, button, key):
        if button.get_active():
            self.target_zone = key

    def on_speed_toggled(self, button, key):
        if button.get_active():
            self.effect_speed = key

    def on_brightness_changed(self, scale):
        self.brightness = int(scale.get_value())

    def on_custom_rgba_changed(self, widget, *_args):
        rgba = widget.get_rgba()
        r = int(round(rgba.red * 255))
        g = int(round(rgba.green * 255))
        b = int(round(rgba.blue * 255))
        self.selected_hex = f'#{r:02x}{g:02x}{b:02x}'

    def on_kbd_zone_rgba_changed(self, widget, *_args):
        z_idx = _args[-1]
        rgba = widget.get_rgba()
        r = int(round(rgba.red * 255))
        g = int(round(rgba.green * 255))
        b = int(round(rgba.blue * 255))
        self.kbd_zone_hexes[z_idx] = f'#{r:02x}{g:02x}{b:02x}'

    def apply_selected_color(self, hex_val):
        self.selected_hex = hex_val
        if self.color_btn:
            rgba = Gdk.RGBA()
            if rgba.parse(hex_val):
                self.color_btn.set_rgba(rgba)
        self.perform([
            'color',
            '--target', self.target_zone,
            '--hex', hex_val.lstrip('#'),
            '--brightness', str(self.brightness),
        ])

    def apply_kbd_zones(self):
        joined = ','.join(h.lstrip('#') for h in self.kbd_zone_hexes)
        self.perform([
            'kbd-zones',
            '--zones-hex', joined,
            '--brightness', str(self.brightness),
        ])

    def start_effect(self, effect_id):
        self.perform([
            'effect',
            '--name', effect_id,
            '--hex', self.selected_hex.lstrip('#'),
            '--speed', self.effect_speed,
            '--brightness', str(self.brightness),
            '--target', self.target_zone,
        ])

    def update_visualizer_css(self, logo_hex, valley_hexes, kbd_hexes=None):
        rules = [
            f'.logo-orb {{ background-color: {logo_hex}; '
            f'box-shadow: 0 0 16px alpha({logo_hex}, 0.85); }}'
        ]
        if kbd_hexes:
            for idx, h in enumerate(kbd_hexes[:4]):
                rules.append(
                    f'.kbd-bar-{idx} {{ background-color: {h}; '
                    f'box-shadow: 0 0 12px alpha({h}, 0.8); }}'
                )
        for idx, h in enumerate(valley_hexes[:16]):
            rules.append(
                f'.valley-bar-{idx} {{ background-color: {h}; '
                f'box-shadow: 0 0 10px alpha({h}, 0.75); }}'
            )
        if self.dynamic_provider:
            self.dynamic_provider.load_from_string('\n'.join(rules))

    def start_visualizer_animation(self, eff):
        self.stop_visualizer_animation()
        self.active_effect = eff
        self.anim_start = time.monotonic()
        self.anim_timer_id = GLib.timeout_add(75, self.animate_visualizer_tick)

    def stop_visualizer_animation(self):
        self.active_effect = None
        if self.anim_timer_id is not None:
            GLib.source_remove(self.anim_timer_id)
            self.anim_timer_id = None

    def animate_visualizer_tick(self):
        if not self.window or not self.active_effect:
            self.anim_timer_id = None
            return GLib.SOURCE_REMOVE
        eff = self.active_effect
        name = eff.get('name', 'breathe')
        speed_mult = {'slow': 0.6, 'normal': 1.0, 'fast': 1.7}.get(eff.get('speed', 'normal'), 1.0)
        bright_scale = max(10, min(100, int(eff.get('brightness', 100)))) / 100.0
        primary = scale_rgb(hex_to_rgb(eff.get('hex', '#00aaff')), bright_scale)
        t = (time.monotonic() - self.anim_start) * speed_mult
        n_blocks = 16

        if name in ('key-ripple', 'key-rainbow', 'key-reactive'):
            # Simulated preview ripple wave across keyboard & wind valley
            center = 1.5 + 1.2 * math.sin(t * 1.3)
            radius = (t * 3.8) % 3.5
            kbd_c = []
            for z in range(4):
                dist = abs(abs(z - center) - radius)
                w = max(0.12, 1.0 - dist * 0.9) if dist < 1.0 else 0.12
                if name == 'key-rainbow':
                    r, g, b = colorsys.hsv_to_rgb((t * 0.25 + z * 0.2) % 1.0, 0.95, w * bright_scale)
                    kbd_c.append(rgb_to_hex((r * 255, g * 255, b * 255)))
                else:
                    kbd_c.append(rgb_to_hex(scale_rgb(primary, w)))
            blocks = []
            for i in range(n_blocks):
                b_pos = (i / float(n_blocks - 1)) * 3.0
                dist = abs(abs(b_pos - center) - radius)
                w = max(0.10, 1.0 - dist * 0.9) if dist < 1.0 else 0.10
                if name == 'key-rainbow':
                    r, g, b = colorsys.hsv_to_rgb((t * 0.25 + i * 0.05) % 1.0, 0.95, w * bright_scale)
                    blocks.append(rgb_to_hex((r * 255, g * 255, b * 255)))
                else:
                    blocks.append(rgb_to_hex(scale_rgb(primary, w)))
            self.update_visualizer_css(kbd_c[1], blocks, kbd_c)

        elif name == 'breathe':
            wave = 0.06 + 0.94 * (0.5 * (1.0 - math.cos(t * 2.4)))
            c = rgb_to_hex(scale_rgb(primary, wave))
            self.update_visualizer_css(c, [c] * n_blocks, [c] * 4)
        elif name == 'breathe-rainbow':
            cycle = t * 0.42
            hue = (int(cycle) * 0.19 + (cycle % 1.0) * 0.08) % 1.0
            wave = 0.05 + 0.95 * (math.sin((cycle % 1.0) * math.pi) ** 1.6)
            r, g, b = colorsys.hsv_to_rgb(hue, 0.95, wave * bright_scale)
            c = rgb_to_hex((r * 255, g * 255, b * 255))
            self.update_visualizer_css(c, [c] * n_blocks, [c] * 4)
        elif name == 'marquee':
            head = int(t * 8.5) % n_blocks
            bg = rgb_to_hex(scale_rgb(primary, 0.07))
            blocks = [bg] * n_blocks
            for offset, weight in enumerate([1.0, 0.62, 0.30, 0.14]):
                blocks[(head - offset) % n_blocks] = rgb_to_hex(scale_rgb(primary, weight))
            kbd_c = [blocks[z * 4 + 1] for z in range(4)]
            dist_center = abs(((head - 8.0 + 8.0) % n_blocks) - 8.0)
            logo_c = rgb_to_hex(scale_rgb(primary, max(0.2, 1.0 - (dist_center / 8.0) * 0.75)))
            self.update_visualizer_css(logo_c, blocks, kbd_c)
        elif name == 'scanner':
            span = (n_blocks - 1) * 2
            pos_raw = (t * 11.0) % span
            head = pos_raw if pos_raw <= (n_blocks - 1) else span - pos_raw
            blocks = []
            for i in range(n_blocks):
                dist = abs(i - head)
                w = 1.0 if dist < 0.8 else (0.55 if dist < 1.8 else (0.22 if dist < 3.0 else 0.05))
                blocks.append(rgb_to_hex(scale_rgb(primary, w)))
            kbd_c = [blocks[z * 4 + 1] for z in range(4)]
            logo_c = rgb_to_hex(scale_rgb(primary, 0.35 + 0.65 * abs(math.sin(t * 2.8))))
            self.update_visualizer_css(logo_c, blocks, kbd_c)
        elif name == 'rainbow-wave':
            blocks = []
            for i in range(n_blocks):
                hue = (i / float(n_blocks) - t * 0.35) % 1.0
                r, g, b = colorsys.hsv_to_rgb(hue, 0.95, bright_scale)
                blocks.append(rgb_to_hex((r * 255, g * 255, b * 255)))
            kbd_c = [blocks[z * 4 + 1] for z in range(4)]
            self.update_visualizer_css(blocks[n_blocks // 2], blocks, kbd_c)
        elif name == 'cyber-pulse':
            c_pink = scale_rgb((255, 0, 127), bright_scale)
            c_cyan = scale_rgb((0, 240, 255), bright_scale)
            logo_c = rgb_to_hex(lerp_rgb(c_pink, c_cyan, (math.sin(t * 3.2) + 1.0) * 0.5))
            blocks = [
                rgb_to_hex(lerp_rgb(c_pink, c_cyan, (math.sin(t * 3.2 + i * 0.45) + 1.0) * 0.5))
                for i in range(n_blocks)
            ]
            kbd_c = [blocks[z * 4 + 1] for z in range(4)]
            self.update_visualizer_css(logo_c, blocks, kbd_c)
        return GLib.SOURCE_CONTINUE

    def do_activate(self):
        if self.window:
            self.window.present()
            return
        self.window = Gtk.ApplicationWindow(application=self, title='灯光控制')
        self.window.set_default_size(780, 840)
        self.window.connect('close-request', self.closed)

        header = Gtk.HeaderBar()
        refresh = Gtk.Button(icon_name='view-refresh-symbolic', tooltip_text='刷新灯光状态')
        refresh.connect('clicked', lambda _button: self.perform(['status']))
        self.buttons.append(refresh)
        header.pack_end(refresh)
        self.window.set_titlebar(header)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        for edge in ('top', 'bottom', 'start', 'end'):
            getattr(content, 'set_margin_' + edge)(18)

        content.append(self.build_visualizer())

        cards = Gtk.Box(spacing=12, homogeneous=True)
        cards.append(self.card('A 面 LOGO', '屏幕背面猎人标志灯', 'logo', 'logo-on', 'logo-off', '默认蓝光'))
        cards.append(self.card('四分区键盘', '机身 RGB 四区背光键盘', 'keyboard', 'kbd-on', 'kbd-off', '原厂四色'))
        cards.append(self.card('风谷灯', '机身升降风谷 70 灯珠灯带', 'valley', 'valley-on', 'valley-off', '默认蓝光'))
        content.append(cards)

        content.append(self.build_color_section())
        content.append(self.build_gradient_section())
        content.append(self.build_dynamic_section())

        all_buttons = Gtk.Box(spacing=10, homogeneous=True)
        all_buttons.append(self.make_action_button('✨ 全机恢复出厂默认灯光', ['all-on'], suggested=True))
        all_buttons.append(self.make_action_button('🌙 全机关闭所有灯光', ['all-off']))
        content.append(all_buttons)

        footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.boot = Gtk.Label(label='支持 LOGO、四分区键盘、70 灯珠风谷灯独立调色与按键涟漪', xalign=0)
        self.boot.add_css_class('dim-label')
        footer.append(self.boot)
        self.message = Gtk.Label(
            label='正在读取当前灯光状态…',
            xalign=0, wrap=True, selectable=True
        )
        footer.append(self.message)
        content.append(footer)

        scroller.set_child(content)
        self.window.set_child(scroller)

        swatch_css = []
        for idx, (_name, hex_val) in enumerate(PRESET_COLORS):
            swatch_css.append(
                f'.swatch-dot-{idx} {{ background-color: {hex_val}; border-radius: 999px; '
                f'box-shadow: 0 0 6px alpha({hex_val}, 0.8); }}'
            )

        base_css = Gtk.CssProvider()
        base_css.load_from_string(
            '.visualizer-card { padding: 16px; border-radius: 14px; '
            'background: alpha(currentColor, 0.04); '
            'border: 1px solid alpha(currentColor, 0.14); } '
            '.logo-orb { border-radius: 999px; border: 2px solid alpha(currentColor, 0.25); } '
            '.kbd-bar { border-radius: 8px; border: 1px solid alpha(currentColor, 0.22); } '
            '.kbd-zone-text { font-size: 0.78em; font-weight: 700; color: #ffffff; '
            'text-shadow: 0 1px 3px rgba(0, 0, 0, 0.85); } '
            '.valley-bar { border-radius: 6px; border: 1px solid alpha(currentColor, 0.18); } '
            '.effect-badge { padding: 4px 10px; border-radius: 999px; '
            'background: alpha(currentColor, 0.09); font-size: 0.85em; font-weight: 600; } '
            '.lamp-card { padding: 16px; border-radius: 14px; '
            'border: 1px solid alpha(currentColor, 0.14); } '
            '.effect-tile { padding: 10px 12px; border-radius: 10px; } '
            '.swatch-btn { padding: 8px 10px; border-radius: 10px; } '
            + '\n'.join(swatch_css)
        )
        Gtk.StyleContext.add_provider_for_display(
            self.window.get_display(), base_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.dynamic_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            self.window.get_display(), self.dynamic_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        self.update_visualizer_css('#00aaff', ['#00aaff'] * 16, self.kbd_zone_hexes)

        if self.self_check:
            print(json.dumps({'title': self.window.get_title(), 'zones': list(self.states),
                              'buttons': len(self.buttons)}, ensure_ascii=False))
            self.quit()
        else:
            self.window.present()
            self.perform(['status'])

    def closed(self, _window):
        self.stop_visualizer_animation()
        self.window = None
        return False

    def perform(self, cmd_args):
        if isinstance(cmd_args, str):
            cmd_args = [cmd_args]
        if self.busy:
            return
        self.busy = True
        for button in self.buttons:
            button.set_sensitive(False)
        self.message.set_label('正在执行灯光指令… 如出现授权窗口，请输入系统密码。')
        self.hold()
        threading.Thread(target=self.worker, args=(list(cmd_args),), daemon=True).start()

    def worker(self, cmd_args):
        result = {}
        error = None
        try:
            process = subprocess.run(
                ['/usr/bin/pkexec', '/usr/local/sbin/honer-lights-gui-helper'] + cmd_args,
                capture_output=True, text=True)
            if process.returncode in (126, 127):
                error = '授权已取消或未通过，请再次点击操作并完成授权。'
            else:
                result = json.loads(process.stdout)
                if process.returncode or not result.get('ok'):
                    error = '操作未完成：' + result.get('error', '请刷新状态后重试。')
        except (OSError, ValueError) as exc:
            error = '无法完成操作：' + str(exc)
        finally:
            GLib.idle_add(self.finished, result, error)

    def finished(self, result, error):
        self.busy = False
        if self.window:
            names = {'off': '已关闭', 'on': '已开启', 'mixed': '分段点亮'}
            colors = result.get('colors', {})
            for zone, label in self.states.items():
                status = result.get('lights', {}).get(zone)
                if status:
                    state_txt = names.get(status['state'], '状态未知')
                    if zone == 'logo' and colors.get('logo'):
                        state_txt += f" · {colors['logo'].upper()}"
                    elif zone == 'keyboard' and status['state'] != 'off':
                        state_txt += f" ({status['lit']}/{status['total']} 区点亮)"
                    elif zone == 'valley' and status['state'] != 'off':
                        state_txt += f" ({status['lit']}/{status['total']} 颗点亮)"
                    label.set_label(state_txt)
                else:
                    label.set_label('未读取状态')

            kbd_c = colors.get('keyboard')
            if kbd_c and len(kbd_c) == 4:
                self.kbd_zone_hexes = list(kbd_c)
                for idx, c_btn in enumerate(self.kbd_color_btns):
                    rgba = Gdk.RGBA()
                    if rgba.parse(kbd_c[idx]):
                        c_btn.set_rgba(rgba)

            active_eff = result.get('active_effect')
            if active_eff:
                speed_names = {'slow': '慢速', 'normal': '标准', 'fast': '极速'}
                spd = speed_names.get(active_eff.get('speed'), '标准')
                self.active_effect_label.set_label(
                    f"⚡ 动态运行中：{active_eff.get('label', active_eff.get('name'))} ({spd})"
                )
                self.start_visualizer_animation(active_eff)
            else:
                self.stop_visualizer_animation()
                self.active_effect_label.set_label('静态硬件模式 (零后台占用)')
                if colors:
                    logo_c = colors.get('logo', '#000000')
                    valley_c = colors.get('valley', ['#000000'] * 16)
                    self.update_visualizer_css(logo_c, valley_c, kbd_c)

            if 'boot_off' in result:
                self.boot.set_label(
                    '开机自动关灯：' + ('已启用' if result['boot_off'] else '未启用')
                    + ' · 支持按键波纹涟漪与全机灯效联动'
                )
            self.message.set_label(error or '已完成，全机灯光状态与色彩预览已同步刷新。')
            for button in self.buttons:
                button.set_sensitive(True)
        self.release()
        return GLib.SOURCE_REMOVE


if __name__ == '__main__':
    check = '--self-check' in sys.argv
    raise SystemExit(LightControl(self_check=check).run([sys.argv[0]]))
