import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import zipfile

from kira_live2d_desktop.model_library import ModelLibrary, safe_relative


def model_files(name='Pet'):
    return {name+'.model3.json': json.dumps({'Version':3,'FileReferences':{'Moc':'pet.moc3','Textures':['textures/0.png']}}).encode(),
            'pet.moc3': b'model fixture', 'textures/0.png': b'texture fixture'}


def uploads(files):
    return [SimpleNamespace(file=io.BytesIO(value)) for value in files.values()]


class ModelLibraryTests(unittest.TestCase):
    def test_import_folder_zip_history_and_repeat_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            library=ModelLibrary(directory); files=model_files()
            first=library.import_files(uploads(files),list(files))
            self.assertTrue(Path(first[0]).is_file())
            self.assertEqual(library.import_files(uploads(files),list(files)),first)
            buffer=io.BytesIO()
            with zipfile.ZipFile(buffer,'w') as archive:
                for name,value in files.items(): archive.writestr(name,value)
            buffer.seek(0)
            self.assertEqual(library.import_files([SimpleNamespace(file=buffer)],['pet.zip']),first)
            items=library.items(None,first[0]);self.assertEqual(len(items),1)
            self.assertEqual(items[0]['name'],'Pet');self.assertTrue(items[0]['current'])
            self.assertTrue(items[0]['available'])

    def test_reimport_repairs_missing_or_broken_cached_resources_and_preserves_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            library=ModelLibrary(directory);files=model_files()
            first=library.import_files(uploads(files),list(files));model=Path(first[0])
            settings=Path(directory)/'model-settings.json';settings.write_text('{"keep":true}')
            (model.parent/'textures/0.png').unlink()
            repaired=library.import_files(uploads(files),list(files))
            self.assertEqual(repaired,first)
            self.assertEqual((model.parent/'textures/0.png').read_bytes(),files['textures/0.png'])
            self.assertEqual(settings.read_text(),'{"keep":true}')
            self.assertEqual(len(library.items(None)),1)
            self.assertTrue(list(library.root.glob('*-previous-*')))
            model.write_text('{"FileReferences":null}')
            self.assertEqual(library.import_files(uploads(files),list(files)),first)
            self.assertEqual(model.read_bytes(),files['Pet.model3.json'])

    def test_missing_resource_does_not_enter_library(self):
        with tempfile.TemporaryDirectory() as directory:
            library=ModelLibrary(directory);files=model_files();files.pop('textures/0.png')
            with self.assertRaisesRegex(ValueError,'资源缺失'):
                library.import_files(uploads(files),list(files))
            self.assertEqual(library.items(None),[])
            self.assertEqual(list(library.root.iterdir()),[])

    def test_archive_traversal_duplicate_and_windows_paths_are_rejected(self):
        for name in ['../outside','/absolute','C:/absolute','a/../../outside','a/CON.txt','a/file:stream','a/.. /x']:
            with self.subTest(name=name),self.assertRaises(ValueError):safe_relative(name)
        with tempfile.TemporaryDirectory() as directory:
            library=ModelLibrary(directory);buffer=io.BytesIO()
            with zipfile.ZipFile(buffer,'w') as archive: archive.writestr('../outside',b'x')
            buffer.seek(0)
            with self.assertRaises(ValueError):library.import_files([SimpleNamespace(file=buffer)],['bad.zip'])
            self.assertFalse((Path(directory)/'outside').exists())
            with self.assertRaisesRegex(ValueError,'重复'):
                library.import_files(uploads({'a':b'1','b':b'2'}),['Pet.json','pet.json'])

    def test_workshop_lpk_requires_config_before_downloading(self):
        from unittest.mock import patch
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as archive:
            archive.writestr('config.mlve',json.dumps({'type':'STM_1_0','list':[]}))
        buffer.seek(0)
        with tempfile.TemporaryDirectory() as directory:
            library=ModelLibrary(directory)
            with patch('kira_live2d_desktop.lpk_engine.ensure_engine') as download:
                with self.assertRaisesRegex(ValueError,'config.json'):
                    library.import_files([SimpleNamespace(file=buffer)],['pet.lpk'])
                download.assert_not_called()
            self.assertEqual(library.items(None),[])

    def test_history_excludes_workshop_config_and_groups_managed_copies_without_changing_current(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'unpacked-models'/'NingNing'/'model0.json'
            source.parent.mkdir(parents=True);source.write_bytes(model_files()['Pet.model3.json'])
            config=root/'config.json';config.write_text(json.dumps({'lpkFile':'pet.lpk'}))
            copies=[]
            for name in ('first','second'):
                folder=root/'ai-models'/name;model=folder/'model'/'model0.json';model.parent.mkdir(parents=True)
                model.write_bytes(source.read_bytes())
                (folder/'adaptation.json').write_text(json.dumps({'model_path':str(model),'original':str(source)}))
                copies.append(model)
            history=SimpleNamespace(models={str(index):{'path':str(path)} for index,path in enumerate([config,source,*copies])})
            items=ModelLibrary(root).items(history,str(copies[1]))
            self.assertEqual(len(items),1)
            self.assertEqual(items[0]['path'],str(copies[1].resolve()))
            self.assertEqual(items[0]['name'],'NingNing · model0')
            self.assertTrue(items[0]['current'])
            self.assertTrue(all(path.is_file() for path in [source,config,*copies]))
