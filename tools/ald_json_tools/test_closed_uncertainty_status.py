import ast,copy,unittest
from pathlib import Path
class StatusHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree=ast.parse(Path(__file__).with_name('convert_ald_json.py').read_text(encoding='utf8'))
        run=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='run')
        calls=[n for n in ast.walk(run)if isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)and isinstance(n.func.value,ast.Name)and n.func.value.id=='item'and n.func.attr=='update']
        expr=next(k.value for c in calls for k in c.keywords if k.arg=='status')
        cls.code=compile(ast.fix_missing_locations(ast.Expression(expr)),'actual-cli-status-expression','eval')
    def classify(self,uncertainties=None,diff=0,questions=None,rendered=b'ok'):
        review={'uncertainties':copy.deepcopy(uncertainties or []),'format questions':questions or []};before=copy.deepcopy(review)
        out=eval(self.code,{'__builtins__':{'any':any}},dict(review=review,comparison={'different cells':diff},rendered=rendered))
        self.assertEqual(review,before);return out
    def test_exact_clean_remains_clean(self):self.assertEqual(self.classify(),'converted')
    def test_closed_source_history_not_current_finding(self):self.assertEqual(self.classify([{'status':'resolved','field':'page/ibm division','resolution':'','authority':'Exact reviewed original blank'}]),'converted')
    def test_open_source_hold_not_cleared(self):self.assertEqual(self.classify([{'status':'unresolved'}]),'converted with findings')
    def test_unknown_or_absent_status_holds(self):
        for row in ({},{'status':None},{'status':'pending'},{'status':'RESOLVED'}):self.assertEqual(self.classify([row]),'converted with findings')
    def test_mixed_closed_open_holds(self):self.assertEqual(self.classify([{'status':'resolved'},{'status':'unresolved'}]),'converted with findings')
    def test_difference_still_finding(self):self.assertEqual(self.classify([{'status':'resolved'}],diff=1),'converted with findings')
    def test_format_question_still_finding(self):self.assertEqual(self.classify([{'status':'resolved'}],questions=[{'field':'unknown'}]),'converted with findings')
    def test_render_failure_still_finding(self):self.assertEqual(self.classify([{'status':'resolved'}],rendered=None),'converted with findings')
