import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('doctor',Path(__file__).with_name('doctor.py'))
doctor=importlib.util.module_from_spec(spec);spec.loader.exec_module(doctor)

class DoctorTests(unittest.TestCase):
    def test_partial_database_is_reported_without_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);profile=root/'.runtime/profile';profile.mkdir(parents=True)
            sentinel=profile/'lab.sqlite';sentinel.write_bytes(b'fictional-existing-data')
            with patch.dict('os.environ',{'CAREER_AGENT_COMMAND':'["not-an-installed-fictional-command"]'}):
                result=doctor.inspect(root)
            self.assertTrue(any(level=='ERROR' and 'Partial' in message for level,message in result))
            self.assertEqual(sentinel.read_bytes(),b'fictional-existing-data')
            self.assertFalse((root/'.runtime/locations.json').exists())
    def test_bad_agent_diagnostics_do_not_echo_private_command(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict('os.environ',{'CAREER_AGENT_COMMAND':'secret-not-json'}):
            result=doctor.inspect(Path(directory))
            self.assertTrue(any(level=='ERROR' and 'Agent' in message for level,message in result))
            self.assertNotIn('secret-not-json',repr(result))
