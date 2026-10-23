import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest

if os.name == 'nt':
    sys.modules.setdefault('fcntl', types.ModuleType('fcntl'))
spec = importlib.util.spec_from_file_location(
    'lights', Path(__file__).with_name('v700-lights.py'))
lights = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lights)


def snapshots():
    result = []
    for selector in range(70):
        reply = bytearray(256)
        reply[:10] = bytes([0, 0xD0, 0, selector, 0, 0, 1, 0, 170, 255])
        result.append({'zone': 'd0', 'selector': selector, 'reply': reply.hex()})
    return result


class ProtocolTests(unittest.TestCase):
    def test_original_off_packets(self):
        packets = lights.off_requests('d0')
        self.assertEqual([tuple(p[4:6]) for p in packets], lights.D0_SEGMENTS)
        for packet in packets:
            self.assertEqual(len(packet), 64)
            self.assertEqual(packet[:4], bytes([6, 5, 0xD0, 0]))
            self.assertEqual(packet[6:9], bytes([1, 44, 1]))
            self.assertFalse(any(packet[9:]))

    def test_restore_preserves_segment_boundaries_and_colors(self):
        data = snapshots()
        packets = lights.restore_requests(data)
        self.assertEqual([tuple(p[4:6]) for p in packets], lights.D0_SEGMENTS)
        self.assertTrue(all(p[9:12] == bytes([0, 170, 255]) for p in packets))
        reply = bytearray.fromhex(data[1]['reply'])
        reply[7] = 255
        data[1]['reply'] = reply.hex()
        self.assertEqual(len(lights.restore_requests(data)), 6)

    def test_incomplete_or_other_zone_backup_is_rejected(self):
        original = lights.BACKUP
        try:
            with tempfile.TemporaryDirectory() as directory:
                lights.BACKUP = Path(directory) / 'original-lighting.json'
                path = lights.backup_path('d0')
                data = snapshots()
                path.write_text(json.dumps(data))
                self.assertEqual(len(lights.validated_backup('d0')), 70)
                path.write_text(json.dumps(data[:-1]))
                with self.assertRaises(RuntimeError):
                    lights.validated_backup('d0')
                data[0]['zone'] = 'logo'
                path.write_text(json.dumps(data))
                with self.assertRaises(RuntimeError):
                    lights.validated_backup('d0')
        finally:
            lights.BACKUP = original

    def test_block_requests_merge_within_segments_only(self):
        # Uniform color across all 16 blocks should merge into the 4 hardware segments
        uniform = [(168, 85, 247)] * 16
        packets = lights.d0_block_requests(uniform)
        self.assertEqual([tuple(p[4:6]) for p in packets], lights.D0_SEGMENTS)
        # Rainbow gradient should produce 1 logo + 4 kbd + 16 d0 block packets
        rainbow_packets = lights.theme_requests('gradient-rainbow', brightness=100)
        self.assertEqual(len(rainbow_packets), 1 + 4 + 16)


if __name__ == '__main__':
    unittest.main()
