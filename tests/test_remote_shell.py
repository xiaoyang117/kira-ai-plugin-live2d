import json,tempfile,unittest,zipfile
from pathlib import Path
from kira_live2d_desktop.native_shell.remote_model import make_model_bundle,unpack_model_bundle

class RemoteBundleTests(unittest.TestCase):
    def test_portable_bundle_preserves_named_and_file_motion_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'original';stage=root/'stage';source.mkdir();(stage/'assets').mkdir(parents=True)
            (stage/'native.model3.json').write_text('{}');(stage/'assets'/'a.json').write_text('{"Curves":[]}')
            model={'path':str(stage/'native.model3.json'),'original':str(source/'pet.json'),
                'motion_files':{str(source/'wave.json'):str(stage/'assets'/'a.json')},'motion_entries':{'Wave':[{'File':'wave.json'}]}}
            archive,digest=make_model_bundle(model,root/'bundles')
            portable,aliases=unpack_model_bundle(archive,root/'client')
            self.assertTrue(Path(portable['path']).is_file())
            original=str(source/'wave.json');self.assertTrue(Path(aliases[original]).is_file())
            self.assertIn(aliases[original],portable['motion_files'])
            self.assertEqual(Path(portable['original']).parent/portable['motion_entries']['Wave'][0]['File'],Path(aliases[original]))
            self.assertEqual(make_model_bundle(model,root/'bundles')[1],digest)
    def test_archive_traversal_and_absolute_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ('../escape','C:/escape','/escape'):
                archive=root/'bad.zip'
                with zipfile.ZipFile(archive,'w') as z:z.writestr(name,'bad')
                with self.assertRaises(ValueError):unpack_model_bundle(archive,root/'client')
