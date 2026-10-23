import importlib.machinery
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).with_name('honer-lights-gui-helper')
if not path.exists():
    path = Path('/usr/local/sbin/honer-lights-gui-helper')
loader = importlib.machinery.SourceFileLoader('gui_helper', str(path))
spec = importlib.util.spec_from_loader(loader.name, loader)
helper = importlib.util.module_from_spec(spec)
loader.exec_module(helper)


def snapshots(zone, lit):
    count, region = {'logo': (1, 0xA0), 'd0': (70, 0xD0)}[zone]
    items = []
    for selector in range(count):
        reply = bytearray(256)
        reply[:7] = bytes([0, region, 0, selector, 0, 0, 1])
        if selector < lit:
            reply[7:10] = bytes([0, 170, 255])
        items.append({'zone': zone, 'selector': selector, 'reply': reply.hex()})
    return items


class StatusTests(unittest.TestCase):
    def test_all_off_and_on(self):
        for zone, total in [('logo', 1), ('d0', 70)]:
            self.assertEqual(helper.summarize(snapshots(zone, 0), zone),
                             {'state': 'off', 'lit': 0, 'total': total})
            self.assertEqual(helper.summarize(snapshots(zone, total), zone)['state'], 'on')

    def test_partial_strip(self):
        self.assertEqual(helper.summarize(snapshots('d0', 20), 'd0'),
                         {'state': 'mixed', 'lit': 20, 'total': 70})

    def test_invalid_reads_not_reported_as_success(self):
        with self.assertRaises(ValueError):
            helper.summarize([], 'd0')
        data = snapshots('d0', 0)
        data[1]['selector'] = 0
        with self.assertRaises(ValueError):
            helper.summarize(data, 'd0')
        data = snapshots('logo', 0)
        data[0]['reply'] = '00'
        with self.assertRaises(ValueError):
            helper.summarize(data, 'logo')

    def test_actions_never_write_keyboard(self):
        for actions in helper.ACTIONS.values():
            self.assertTrue(all(zone in ('logo', 'd0') for zone, _ in actions))

    def test_extract_colors(self):
        lights = helper.load_lights_module()
        colors = helper.extract_colors(snapshots('logo', 1), snapshots('d0', 70), lights.D0_BLOCKS)
        self.assertEqual(colors['logo'], '#00aaff')
        self.assertEqual(len(colors['valley']), 16)
        self.assertTrue(all(c == '#00aaff' for c in colors['valley']))


if __name__ == '__main__':
    unittest.main()
