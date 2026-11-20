"""Offline tests of generated USB/HAT configuration; no device access."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch

import create_image
import prepare_image
import prepare_runtime
from serial_config import bus_port_config, deploy_serial_source, validate_port


class SerialConfiguration(unittest.TestCase):
    def test_preserves_unrelated_settings_and_comments(self):
        source = ('# unit\n["bus"] # link\n"port" = "/dev/ttyS2" # keep\n'
                  'baudrate = 1000000\n[policy]\nenabled = false\n'
                  '[other]\nport = "unchanged"\n')
        result = bus_port_config(source, '/dev/ttyACM0')
        self.assertIn('# keep', result)
        self.assertEqual(tomllib.loads(result)['other']['port'], 'unchanged')
        self.assertFalse(tomllib.loads(result)['policy']['enabled'])
        self.assertEqual(tomllib.loads(result)['bus'], {'port': '/dev/ttyACM0', 'baudrate': 1000000})
        self.assertEqual(bus_port_config(result, '/dev/ttyACM0'), result)

    def test_missing_or_unsupported_assignment_refused(self):
        for source in ('[bus]\nbaudrate=1000000\n', 'bus.port = "/dev/ttyS2"\n'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                bus_port_config(source, '/dev/ttyACM0')

    def test_invalid_ports_refused(self):
        for port in ('sim', '/dev/ttyACM0 --commissioning', '/dev/ttyACM0\nExecStart=bad'):
            with self.subTest(port=port), self.assertRaises(ValueError):
                validate_port(port)

    def test_helper_and_updater_use_selected_bus_without_clobbering_config(self):
        deploy = Path(__file__).resolve().parents[2] / 'software/studio/deploy'
        helper = deploy_serial_source((deploy / 'microduck-helper').read_text(encoding='utf-8'), '/dev/ttyACM0', 'helper')
        updater = deploy_serial_source((deploy / 'native_update.py').read_text(encoding='utf-8'), '/dev/ttyACM0', 'updater')
        self.assertIn('PORT = "/dev/ttyACM0"', helper)
        self.assertIn("ARGS = [TARGET, '--socket', '/run/robotd.sock', '--params', CONFIG]", updater)
        compile(helper, 'helper', 'exec')
        compile(updater, 'updater', 'exec')

    def test_unrecognized_deploy_baseline_refused(self):
        for kind in ('helper', 'updater'):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                deploy_serial_source('unknown source', '/dev/ttyACM0', kind)

    def test_studio_unit_preserves_other_arguments(self):
        for port in ('/dev/ttyACM0', '/dev/ttyS2'):
            unit = prepare_image.studio_unit(port)
            self.assertIn('--servo-port ' + port + '\n', unit)
            self.assertIn('--state-dir /var/lib/microduck-studio', unit)
            self.assertIn('SupplementaryGroups=robot dialout audio', unit)
            self.assertEqual(unit.count('ExecStart='), 1)

    def fixture(self, root):
        runtime = root / prepare_runtime.RUNTIME
        runtime.mkdir(parents=True)
        settings = ['[bus]', 'port = "/dev/ttyS2"', 'baudrate = 1000000', '[policy]', 'enabled = true']
        for slot, ident in prepare_runtime.CAPABILITIES.items():
            key = 'sitstand' if slot == 'sit_stand' else slot
            rel = prepare_runtime.RUNTIME / 'models' / ident / 'policy.onnx'
            model = root / rel
            model.parent.mkdir(parents=True)
            model.write_bytes(b'test model, never executed')
            settings.append(key + ' = "/' + rel.as_posix() + '"')
        (runtime / 'robotd-profile.toml').write_text('\n'.join(settings) + '\n')
        calibration = ('motion_enabled = false\nimu_mount_verified = false\nunits_verified = false\n'
                       + ''.join('[[joints]]\ncalibrated = false\nzero_raw = 2048\n' for _ in range(15)))
        (runtime / 'hd1910-calibration.template.toml').write_text(calibration)

    def test_new_image_configs_agree_and_motion_authorization_is_not_added(self):
        for port in ('/dev/ttyACM0', '/dev/ttyS2'):
            with self.subTest(port=port), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.fixture(root)
                # Windows development hosts need not grant symlink creation privileges.
                with patch.object(Path, 'symlink_to'):
                    prepare_runtime.configure_new_unit(root, port)
                for name in ('robotd.toml', 'robotd.saved.toml'):
                    data = tomllib.loads((root / prepare_runtime.CONFIG / name).read_text())
                    self.assertEqual(data['bus']['port'], port)
                    self.assertEqual(data['bus']['baudrate'], 1000000)
                unit = (root / 'etc/systemd/system/robotd.service').read_text()
                self.assertEqual('ExecStartPre=' in unit, port == '/dev/ttyS2')
                commissioning = (root / 'etc/systemd/system/robotd.service.d/zzzz-zz-microduck-commissioning.conf').read_text()
                self.assertIn('--commissioning', commissioning)
                data = tomllib.loads((root / prepare_runtime.CONFIG / 'hd1910-calibration.toml').read_text())
                self.assertFalse(data['motion_enabled'])
                self.assertFalse((root / 'var/lib/microduck-studio/servo-session.json').exists())

    def test_create_cli_default_and_hat_override(self):
        for extra, port in (([], '/dev/ttyACM0'), (['--servo-port', '/dev/ttyS2'], '/dev/ttyS2')):
            with patch('sys.argv', ['create_image.py', '--base', 'base.img', '--output', 'out.img', *extra]), patch.object(create_image, 'create', return_value={}) as run, contextlib.redirect_stdout(io.StringIO()):
                create_image.main()
                self.assertEqual(run.call_args.args[0].servo_port, port)


if __name__ == '__main__':
    unittest.main()
