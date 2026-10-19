import sys,json,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from kira_live2d_desktop.resource_policy import read_policy,apply_analysis,allowed

class UnknownDefaults(unittest.TestCase):
    def test_defaults_and_explicit_choices(self):
        analysis={'motions':{'unknown':{'uncertain':True},'nod':{'uncertain':False},'dress':{'uncertain':True,'appearance':True}}}
        raw=read_policy('')
        policy=apply_analysis(raw,analysis)
        self.assertFalse(allowed(policy,'motions','unknown'))
        self.assertTrue(allowed(policy,'motions','nod'))
        self.assertTrue(allowed(policy,'motions','dress'))
        self.assertEqual(raw['disabled_motions'],[])
        raw['enabled_motions']=['unknown']
        raw=read_policy(json.dumps(raw))
        self.assertTrue(allowed(apply_analysis(raw,analysis),'motions','unknown'))
        raw['disabled_motions']=['unknown']
        self.assertFalse(allowed(apply_analysis(raw,analysis),'motions','unknown'))
    def test_new_resources_and_rescan(self):
        raw=read_policy(json.dumps({'enabled_expressions':['old']}))
        analysis={'expressions':{'old':{'uncertain':True},'new':{'uncertain':True}}}
        for _ in range(2):
            effective=apply_analysis(raw,analysis)
            self.assertTrue(allowed(effective,'expressions','old'))
            self.assertFalse(allowed(effective,'expressions','new'))
        self.assertTrue(allowed(effective,'expressions','默认'))

    def test_manual_outfit_classification_preserves_disabled_choices(self):
        from kira_live2d_desktop.resource_policy import apply_appearance
        source={'expressions':{'编号':{'uncertain':True,'appearance':False,'summary':'unknown'}}}
        policy=read_policy(json.dumps({'appearance_expressions':['编号']}))
        marked=apply_appearance(source,policy)
        self.assertTrue(marked['expressions']['编号']['appearance'])
        self.assertFalse(source['expressions']['编号']['appearance'])
        self.assertTrue(allowed(apply_analysis(policy,marked),'expressions','编号'))
        policy['disabled_expressions']=['编号']
        self.assertFalse(allowed(apply_analysis(policy,marked),'expressions','编号'))
