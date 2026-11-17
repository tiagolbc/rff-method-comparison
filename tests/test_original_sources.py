"""Run with Python's standard library: python -m unittest discover -s tests -v."""
from pathlib import Path
import hashlib,json,unittest
ROOT=Path(__file__).resolve().parents[1]
class OriginalSourceRetention(unittest.TestCase):
 def test_original_source_files_match_supplied_archive_baseline(self):
  baseline=json.loads((ROOT/'tests/original_source_baseline.json').read_text())
  self.assertGreater(len(baseline['Files']),10)
  for item in baseline['Files']:
   with self.subTest(path=item['Path']):
    p=ROOT/item['Path'];data=p.read_bytes()
    if p.suffix!='.mat':data=data.decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n').encode()
    self.assertEqual(hashlib.sha256(data).hexdigest(),item['Original_normalized_SHA256'])
 def test_roi_adapters_are_separate_from_original_entry_points(self):
  for item in ['aRFF_AP_ROI_bridge/dependencies/find_RFFcycles_aswipep_roi_native.m','aRFF_AP_ROI_bridge/dependencies/find_RFFcycles_aswipep.m','rff_auto_mb_roi_bridge/RFF_auto_MB_ROI_bridge.m','rff_auto_mb_roi_bridge/RFF_auto_MB_original_unmodified.m']:
   self.assertTrue((ROOT/item).is_file(),item)
if __name__=='__main__':unittest.main()

