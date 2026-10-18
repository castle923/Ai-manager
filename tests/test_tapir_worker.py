"""Fresh contract and CPU checks; GPU E2E is a separate explicit gate."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from ai_manager.tapir_safe import parameters, load_checkpoint, decode_video, validate_outputs


class TrackingContractTests(unittest.TestCase):
    def test_normalized_points_keep_corner_and_center(self):
        value = {'points': [{'x': 0, 'y': 1}, {'x': .5, 'y': .25}], 'max_frames': 32, 'resize': 256}
        self.assertEqual(parameters(value), (value['points'], 32))

    def test_points_and_bounds_reject_nonfinite_bool_and_overflow(self):
        for coordinate in (float('nan'), float('inf'), True, -.01, 1.001, '0.5'):
            with self.subTest(coordinate=coordinate), self.assertRaisesRegex(ValueError, 'tracking_points_invalid'):
                parameters({'points': [{'x': coordinate, 'y': .5}]})
        for invalid in ({'points': []}, {'points': [{'x': .5, 'y': .5}] * 9},
                        {'points': [{'x': .5, 'y': .5}], 'max_frames': 33},
                        {'points': [{'x': .5, 'y': .5}], 'resize': 512},
                        {'points': [{'x': .5, 'y': .5}], 'url': 'https://example.com'}):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                parameters(invalid)

    def test_official_vendor_manifest_matches_current_bytes(self):
        vendor = Path(__file__).resolve().parents[1] / 'src/ai_manager/tapir_vendor'
        manifest = json.loads((vendor / 'PROVENANCE.json').read_text('utf-8-sig'))
        self.assertEqual(manifest['revision'], '730cda1c730877cfedbe01bf87fb1cadb78a565d')
        self.assertEqual({item['file'] for item in manifest['files']}, {'tapir_model.py', 'nets.py', 'utils.py', 'LICENSE'})
        for item in manifest['files']:
            self.assertEqual(hashlib.sha256((vendor / item['file']).read_bytes()).hexdigest(), item['vendored_sha256'])


@unittest.skipUnless(importlib.util.find_spec('torch'), 'requires isolated tracking CPU dependencies')
class CheckpointTests(unittest.TestCase):
    def test_weights_only_true_and_strict_state(self):
        import torch
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fresh.pt'
            model = torch.nn.Linear(2, 1)
            torch.save(model.state_dict(), path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with patch('ai_manager.tapir_safe.CHECKPOINT_BYTES', path.stat().st_size), patch.object(torch, 'load', wraps=torch.load) as loader:
                self.assertEqual(load_checkpoint(torch, model, path, digest), digest)
                self.assertTrue(loader.call_args.kwargs['weights_only'])
                self.assertEqual(loader.call_args.kwargs['map_location'], 'cpu')

    def test_hash_rejected_before_deserialization(self):
        import torch
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fresh.pt'
            path.write_bytes(b'not a checkpoint')
            with patch('ai_manager.tapir_safe.CHECKPOINT_BYTES', path.stat().st_size), patch.object(torch, 'load') as loader:
                with self.assertRaisesRegex(ValueError, 'hash_mismatch'):
                    load_checkpoint(torch, None, path, '0' * 64)
                loader.assert_not_called()

    def test_checkpoint_nan_and_wrong_keys_rejected(self):
        import torch
        for state in ({'weight': torch.tensor([[float('nan'), 1.]]), 'bias': torch.zeros(1)}, {'wrong': torch.zeros(1)}):
            with self.subTest(keys=list(state)), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'fresh.pt'
                torch.save(state, path)
                with patch('ai_manager.tapir_safe.CHECKPOINT_BYTES', path.stat().st_size):
                    with self.assertRaisesRegex(ValueError, 'checkpoint_invalid'):
                        load_checkpoint(torch, torch.nn.Linear(2, 1), path, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_output_shape_nonfinite_and_occlusion(self):
        import torch
        output = {'tracks': torch.zeros(1, 2, 3, 2), 'occlusion': torch.full((1, 2, 3), -10.), 'expected_dist': torch.full((1, 2, 3), -10.)}
        tracks, occluded = validate_outputs(torch, output, 2, 3)
        self.assertEqual(len(tracks), 2)
        self.assertFalse(any(any(row) for row in occluded))
        output['tracks'][0, 0, 0, 0] = float('nan')
        with self.assertRaisesRegex(ValueError, 'output_invalid'):
            validate_outputs(torch, output, 2, 3)
        output['tracks'] = torch.zeros(1, 2, 4, 2)
        with self.assertRaisesRegex(ValueError, 'output_invalid'):
            validate_outputs(torch, output, 2, 3)


@unittest.skipUnless(all(importlib.util.find_spec(name) for name in ('av', 'numpy', 'PIL')), 'requires isolated tracking decode dependencies')
class VideoTests(unittest.TestCase):
    def make_video(self, path, count=3):
        import av
        import numpy as np
        with av.open(str(path), 'w') as writer:
            stream = writer.add_stream('mpeg4', rate=8)
            stream.width, stream.height, stream.pix_fmt = 320, 240, 'yuv420p'
            for index in range(count):
                image = np.zeros((240, 320, 3), dtype=np.uint8)
                image[32:48, 20 + index:36 + index] = 255
                frame = av.VideoFrame.from_ndarray(image, format='rgb24')
                for packet in stream.encode(frame):
                    writer.mux(packet)
            for packet in stream.encode():
                writer.mux(packet)

    def test_new_video_decode_and_resize_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fresh.mp4'
            self.make_video(path)
            frames, source = decode_video(path, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(frames.shape, (3, 256, 256, 3))
            self.assertEqual((source['width'], source['height'], source['frames']), (320, 240, 3))
            self.assertEqual(source['resize']['aspect'], 'stretch')
            with self.assertRaisesRegex(ValueError, 'resource_limit'):
                decode_video(path, hashlib.sha256(path.read_bytes()).hexdigest(), limit=2)
            with self.assertRaisesRegex(ValueError, 'input_changed'):
                decode_video(path, '0' * 64)

    def test_oversized_file_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fresh.mp4'
            with path.open('wb') as writer:
                writer.truncate(5 * 1024 * 1024 + 1)
            with self.assertRaisesRegex(ValueError, 'input_video_invalid'):
                decode_video(path, '0' * 64)


if __name__ == '__main__':
    unittest.main()
