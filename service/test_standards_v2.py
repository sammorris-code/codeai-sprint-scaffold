#!/usr/bin/env python3
"""Synthetic end-to-end tests for lesson/unit/course evidence semantics."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from service.app.standards_v2 import pathways, inventory, alignment, performances, rollup, pipeline, presentation
from service.app.alignment_evidence.sources import digest


def lesson(lid='u::L1', unit='u', choices=False):
    levels = [{'level_name':'task', 'level_type':'Pythonlab', 'student_text':'Design your own function and test it independently.', 'context':{}}]
    if choices:
        levels = [{'level_name':'pick', 'level_type':'bubble_choice', 'student_text':'Choose a grid size for your project.', 'context':{}}] + [
            {'level_name':name,'level_type':'Pythonlab','student_text':'Design your own function and test it independently.',
             'context':{'is_choice_option':True,'choice_parent':'pick'}} for name in ['small','large']]
    return {'stable_id':lid,'lesson_name':lid,'script_name':unit,'unit_name':unit,'absolute_position':1,
            'unit_position':1,'content_hash':'fixture','plan':{},'levels':levels}


def spec(integrated=False):
    return {'standard_id':'DEMO.A','statement':'Design functions and test them.', 'integration_required':integrated,
            'integration_reason':'The performance must combine design and testing.' if integrated else '',
            'requirements':[{'requirement_id':'R1','quote':'Design functions and ', 'required_performance':'Design functions.',
                             'action':'Design','subject':'functions','conditions':'','contributions':['Identify functions'],
                             'insufficient_for_full':['Exposure only'],'not_evidence':['Unrelated topic']},
                            {'requirement_id':'R2','quote':'test them.','required_performance':'Test the functions.',
                             'action':'Test','subject':'functions','conditions':'','contributions':['Discuss testing'],
                             'insufficient_for_full':['Exposure only'],'not_evidence':['Unrelated topic']}]}


def item(i='u::L1#I1', conditions=None, kind='practice', lid='u::L1'):
    return {'item_id':i,'lesson_id':lid,'kind':kind,'student_action':'Design a function.',
            'subject':'functions','independence':'independent','conditions':conditions or {},
            'expected_artifact':'program','citations':[]}


def finding(rid='R1', support='full', sets=None):
    return {'requirement_id':rid,'support':support,'depth':'supported_practice' if support in ['full','partial'] else 'exposure',
            'rationale':'The visible task supports this contribution.','missing':'Testing is not yet established.' if support=='partial' else '',
            'evidence_sets':sets if sets is not None else ([['u::L1#I1']] if support!='none' else []),'assessment_sets':[]}


def answer(first=None, second=None, integrated=None):
    return {'verdicts':[{'standard_id':'DEMO.A','findings':[first or finding(), second or finding('R2','none')],
                        'integrated_evidence_sets':integrated or [],'integration_rationale':'Same task requires the whole performance.',
                        'boundary_issue':''}]}


def inv_answer(e):
    source = next(s for s in e['sources'] if 'Design your own' in s['text'])
    return {'items':[{'item_id':'I1','kind':'practice','student_action':'Design and test a function.',
                     'subject':'functions','expected_artifact':'program','independence':'independent',
                     'citations':[{'source_id':source['source_id'],'quote':source['text']}]}],
            'source_dispositions':[{'source_id':s['source_id'],'disposition':'captured' if s is source else 'background'} for s in e['sources']],
            'uncertainties':[]}


class Tests(unittest.TestCase):
    def test_cli_live_stub_then_free_cache_replay(self):
        from service import standards_pipeline
        from service.app.alignment_evidence.data import TABLES
        raw=lesson();raw.update(id=1,snapshot_id=1,unit_id=1,has_lesson_plan=True)
        std={'id':1,'set_id':1,'identifier':'DEMO.A','statement':spec()['statement'],'hierarchy_role':'standard'}
        dataset={table:[] for table in TABLES}
        dataset.update(run=[{'id':1,'set_id':1,'course_id':1,'snapshot_id':1,'scope_note':'Demo'}],
            course=[{'id':1,'course_name':'Demo course'}],snapshot=[{'id':1,'source_commit':'synthetic'}],
            standards_set=[{'id':1,'title':'Demo'}],standard=[std],lesson=[raw],
            unit=[{'id':1,'snapshot_id':1,'script_name':'u','unit_name':'Unit'}],
            course_unit=[{'course_id':1,'unit_id':1,'position':1}],
            standard_outcome=[{'run_id':1,'standard_id':1,'in_scope':True,'outcome':'developed'}])
        def model(client,model,rules,prefix,payload,schema,usage):
            usage['calls']=usage.get('calls',0)+1
            if rules==inventory.RULES:return inv_answer(payload)
            if rules==inventory.UNIT_RULES:return {'summary':'Practice functions.','progression':[{'description':'Design and test.','item_ids':['u::L1#I1']}],'culminating_item_ids':[],'uncertainties':[]}
            if rules==performances.RULES:return {'standards':[spec()]}
            if rules==alignment.DISCOVERY_RULES:return {'candidates':[]}
            if rules==alignment.UNIT_RULES:return answer(second=finding('R2'))
            raise AssertionError(rules)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'data.json').write_text(json.dumps(dataset))
            args=['--dataset',str(root/'data.json'),'--baseline-run','1','--model','stub','--cache',str(root/'cache')]
            with patch.dict(sys.modules,{'anthropic':SimpleNamespace(Anthropic=lambda:object())}), patch.dict(os.environ,{'ANTHROPIC_API_KEY':'synthetic'}), patch('service.app.standards_v2.pipeline.judge.call',side_effect=model):
                self.assertEqual(standards_pipeline.main(args+['--live','--out',str(root/'live')]),0)
            self.assertEqual(standards_pipeline.main(args+['--replay-cache','--out',str(root/'replay')]),0)
            a=json.loads((root/'live/report.json').read_text());b=json.loads((root/'replay/report.json').read_text())
            self.assertEqual(a['state']['coverage'],b['state']['coverage'])
            self.assertEqual(a['state']['coverage']['course']['DEMO.A']['coverage'],'full')
            self.assertEqual(b['manifest']['usage'],{})
            self.assertTrue((root/'live/report.html').exists())

    def test_baseline_runner_uses_defined_standards_and_does_not_write_gaps_on_failure(self):
        from service import align
        executed=[]
        class Connection:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def commit(self):pass
            def execute(self,sql,params=None):
                executed.append(sql)
                if 'SELECT * FROM standards_set' in sql:row={'framework':'DEMO','standard_set':'Test','framework_year':'2026','boundary_provenance':'drafted'}
                elif 'SELECT * FROM course' in sql:row={'course_name':'Demo','snapshot_id':1}
                else:row={'id':1}
                return SimpleNamespace(fetchone=lambda:row)
        raw=lesson();raw.update(id=1,has_lesson_plan=True,has_objectives=False,relative_position=1)
        std={'identifier':'DEMO.A','statement':spec()['statement'],'concept':'Programming'}
        with patch.object(align.psycopg,'connect',return_value=Connection()), patch.object(align,'fetch_standards',return_value=[std]), patch.object(align,'fetch_lessons',return_value=[raw]), patch.object(align.engine,'load_key',return_value=True), patch.dict(sys.modules,{'anthropic':SimpleNamespace(Anthropic=lambda:object())}):
            with patch.object(align.engine,'judge',return_value={'claims':[],'considered_and_rejected':[]}) as judge_mock:
                self.assertEqual(align.main(['--set','1','--course','1','--scope','Demo']),0)
                self.assertIn('DEMO.A',judge_mock.call_args.args[1])
            executed.clear()
            with patch.object(align.engine,'judge',side_effect=RuntimeError('synthetic failure')):
                self.assertEqual(align.main(['--set','1','--course','1','--scope','Demo']),1)
            self.assertFalse(any('INSERT INTO standard_outcome' in sql for sql in executed))

    def test_review_api_rejects_stale_evidence_and_unknown_outcomes(self):
        from service.app.standards_v2 import api
        from fastapi import HTTPException
        from contextlib import contextmanager
        document={'state':{'coverage':{'course':{'DEMO.A':{}},'units':{}}}}
        record={'source_fingerprint':'current','payload':document}
        class Conn:
            def execute(self,sql,params):return SimpleNamespace(fetchone=lambda:record if sql.startswith('SELECT') else {'id':7})
        @contextmanager
        def connection():yield Conn()
        values=dict(source_fingerprint='old',scope='course',standard_id='DEMO.A',decision='accept',actor='Reviewer',reason='Verified source tasks')
        with patch.object(api.pool,'connection',connection):
            with self.assertRaises(HTTPException) as caught:api.review(1,api.Review(**values))
            self.assertEqual(caught.exception.status_code,409)
            values['source_fingerprint']='current';values['standard_id']='unknown'
            with self.assertRaises(HTTPException) as caught:api.review(1,api.Review(**values))
            self.assertEqual(caught.exception.status_code,422)
            values['standard_id']='DEMO.A'
            self.assertFalse(api.review(1,api.Review(**values))['published'])

    def test_equivalent_alternatives_cover_every_path(self):
        self.assertTrue(pathways.universal([{'grid':'small'},{'grid':'large'}],{'grid':['small','large']}))
        self.assertFalse(pathways.universal([{'grid':'small'}],{'grid':['small','large']}))

    def test_mutually_exclusive_requirements_cannot_form_course_coverage(self):
        self.assertFalse(pathways.compatible([[{'choice':'a'}],[{'choice':'b'}]]))
        self.assertIsNone(pathways.join({'choice':'a'},{'choice':'b'}))

    def test_independent_choices_and_solver_budget(self):
        clauses=[{'x':x,'y':y} for x in ['a','b'] for y in ['c','d']]
        self.assertTrue(pathways.universal(clauses, {'x':['a','b'],'y':['c','d']}))
        self.assertIsNone(pathways.universal(clauses, {'x':['a','b'],'y':['c','d']},budget=0))

    def test_bonus_and_unresolved_alternate_are_not_shared(self):
        raw=lesson();raw['levels'][0]['context']['is_bonus']=True;raw['lesson_group_name']='Alternate version'
        routes=pathways.context([raw]);condition=routes['levels'][(raw['stable_id'],'task')]
        self.assertFalse(pathways.universal([condition],routes['domains']))
        self.assertEqual(len(routes['warnings']),1)

    def test_nested_choices_retain_parent_route(self):
        raw=lesson(choices=True)
        raw['levels'] += [{'level_name':'nested','level_type':'Panels','student_text':'Explain this design choice.',
                           'context':{'is_choice_option':True,'choice_parent':'small'}}]
        routes=pathways.context([raw]);condition=routes['levels'][(raw['stable_id'],'nested')]
        self.assertEqual(condition['choice:u::L1:pick'],'small')

    def test_explicit_whole_lesson_alternatives(self):
        a,b=lesson(),lesson('u::L2')
        routes=pathways.context([a,b],{'domains':{'track':['a','b']},'lessons':{'u::L1':{'track':'a'},'u::L2':{'track':'b'}}})
        self.assertFalse(pathways.universal([routes['lessons']['u::L1']],routes['domains']))
        self.assertTrue(pathways.universal(list(routes['lessons'].values()),routes['domains']))

    def test_inventory_preserves_raw_sources_and_rejects_fabricated_quote(self):
        raw=lesson();e=inventory.prepare(raw,pathways.context([raw]));a=inv_answer(e)
        checked=inventory.validate(a,e)
        self.assertEqual(checked['items'][0]['item_id'],'u::L1#I1')
        a['items'][0]['citations'][0]['quote']='A task that does not exist anywhere.'
        with self.assertRaises(ValueError):inventory.validate(a,e)

    def test_inventory_must_account_for_every_source(self):
        raw=lesson();e=inventory.prepare(raw,pathways.context([raw]));a=inv_answer(e);a['source_dispositions']=[]
        with self.assertRaises(ValueError):inventory.validate(a,e)

    def test_inventory_cannot_collapse_different_branches(self):
        raw=lesson(choices=True);e=inventory.prepare(raw,pathways.context([raw]));a=inv_answer(e)
        second=e['sources'][2];a['items'][0]['citations'].append({'source_id':second['source_id'],'quote':second['text']})
        a['source_dispositions'][2]['disposition']='captured'
        with self.assertRaises(ValueError):inventory.validate(a,e)

    def test_unit_summary_cannot_invent_a_final_assessment(self):
        inv={'items':[item()]}
        with self.assertRaises(ValueError):inventory.validate_unit({'progression':[], 'culminating_item_ids':['u::L1#I1']},[inv])

    def test_performance_interpretation_preserves_whole_statement(self):
        performances.validate([spec()],[{'identifier':'DEMO.A','statement':spec()['statement']}])
        bad=spec();bad['requirements'].pop()
        with self.assertRaises(ValueError):performances.validate([bad],[{'identifier':'DEMO.A','statement':spec()['statement']}])

    def test_qualification_missing_candidates_or_items_fails(self):
        with self.assertRaises(ValueError):alignment.qualify({'verdicts':[]},[spec()],[item()],'lesson')
        with self.assertRaises(ValueError):alignment.qualify(answer(first=finding(sets=[['unknown']])),[spec()],[item()],'lesson')

    def test_qualification_rejects_impossible_evidence_set(self):
        items=[item('a',{'grid':'small'}),item('b',{'grid':'large'})]
        with self.assertRaises(ValueError):alignment.qualify(answer(first=finding(sets=[['a','b']])),[spec()],items,'lesson')

    def test_equivalent_options_keep_depth_and_shared_coverage(self):
        items=[item('a',{'grid':'small'}),item('b',{'grid':'large'})]
        f=finding(sets=[['a'],['b']]);f['depth']='independent_performance'
        checked=alignment.qualify(answer(first=f),[spec()],items,'lesson')
        result=rollup.summarize([spec()],checked,{'grid':['small','large']},True)['DEMO.A']
        self.assertTrue(result['requirements']['R1']['full_on_all_paths'])
        self.assertEqual(checked[0]['findings'][0]['depth'],'independent_performance')

    def test_course_can_combine_complementary_units(self):
        specs=[spec()];items=[item()]
        a=alignment.qualify(answer(),specs,items,'lesson')
        b=alignment.qualify(answer(first=finding(support='none'),second=finding('R2')),specs,items,'lesson')
        self.assertEqual(rollup.summarize(specs,a,{},True)['DEMO.A']['coverage'],'partial')
        self.assertEqual(rollup.summarize(specs,a+b,{},True)['DEMO.A']['coverage'],'full')

    def test_partial_repetition_never_becomes_full(self):
        checked=alignment.qualify(answer(first=finding(support='partial')),[spec()],[item()],'lesson')
        self.assertEqual(rollup.summarize([spec()],checked*4,{},True)['DEMO.A']['coverage'],'partial')

    def test_exposure_and_prerequisite_remain_visible(self):
        for support,expected in [('exposure','exposure_only'),('prerequisite','supporting_only')]:
            checked=alignment.qualify(answer(first=finding(support=support)),[spec()],[item(kind='exposure')],'lesson')
            self.assertEqual(rollup.summarize([spec()],checked,{},True)['DEMO.A']['coverage'],expected)

    def test_compound_standard_requires_integration_witness(self):
        s=spec(True);checked=alignment.qualify(answer(second=finding('R2')),[s],[item()],'unit')
        self.assertEqual(rollup.summarize([s],checked,{},True)['DEMO.A']['coverage'],'components_only')
        checked=alignment.qualify(answer(second=finding('R2'),integrated=[['u::L1#I1']]),[s],[item()],'unit')
        self.assertEqual(rollup.summarize([s],checked,{},True)['DEMO.A']['coverage'],'full')

    def test_integration_does_not_infer_project_from_prior_lessons(self):
        with self.assertRaises(ValueError):alignment.qualify(answer(integrated=[['a','b']]),[spec(True)],
            [item('a',lid='u::L1'),item('b',lid='u::L2'),item()],'unit')

    def test_partial_processing_keeps_absence_unknown(self):
        self.assertEqual(rollup.summarize([spec()],[],{},False)['DEMO.A']['coverage'],'unknown')

    def test_all_standard_unit_pass_recovers_discovery_miss_and_reuses_inventory(self):
        raw=lesson();routes=pathways.context([raw]);e=inventory.prepare(raw,routes);specs=[spec()]
        counters={}
        class StubCalls:
            def ask(self,stage,rules,prefix,payload,schema,validator):
                counters[stage]=counters.get(stage,0)+1
                if stage=='inventory':a=inv_answer(payload)
                elif stage=='unit_summary':a={'summary':'Practice a function.', 'progression':[{'description':'Design then test.','item_ids':['u::L1#I1']}], 'culminating_item_ids':[], 'uncertainties':[]}
                elif stage=='discovery':a={'candidates':[]}
                elif stage=='unit_qualification':a=answer(second=finding('R2'))
                else:raise AssertionError(stage)
                return validator(a)
        result=pipeline.run([e],[{'identifier':'DEMO.A','statement':spec()['statement']}],routes,StubCalls(),supplied_specs=specs)
        self.assertEqual(counters.get('lesson_qualification',0),0)
        self.assertEqual(counters['unit_qualification'],1)
        self.assertEqual(result['coverage']['course']['DEMO.A']['coverage'],'full')
        self.assertEqual(result['coverage']['units']['u']['outcomes']['DEMO.A']['coverage'],'full')

    def test_cached_stage_is_revalidated_and_source_changes_invalidate(self):
        raw=lesson();e=inventory.prepare(raw,pathways.context([raw]))
        with tempfile.TemporaryDirectory() as tmp:
            calls=pipeline.Calls(None,'stub',tmp,True)
            with patch('service.app.standards_v2.pipeline.judge.call',return_value=inv_answer(e)) as mocked:
                calls.ask('inventory',inventory.RULES,'shared',e,inventory.SCHEMA,lambda a:inventory.validate(a,e))
                self.assertEqual(mocked.call_count,1)
            replay=pipeline.Calls(None,'stub',tmp,False)
            replay.ask('inventory',inventory.RULES,'shared',e,inventory.SCHEMA,lambda a:inventory.validate(a,e))
            e['sources'][0]['text']+=' Changed.'
            with self.assertRaises(LookupError):replay.ask('inventory',inventory.RULES,'shared',e,inventory.SCHEMA,lambda a:inventory.validate(a,e))

    def test_cache_does_not_save_invalid_synthesis(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=pipeline.Calls(None,'stub',tmp,True)
            with patch('service.app.standards_v2.pipeline.judge.call',return_value={}), self.assertRaises(ValueError):
                calls.ask('test','rules',{}, {}, {},lambda a:(_ for _ in ()).throw(ValueError('bad')))
            self.assertFalse(list(Path(tmp).glob('*.json')))

    def test_unit_missing_lesson_keeps_evidence_incomplete(self):
        raw=lesson();e=inventory.prepare(raw,pathways.context([raw]));inv=inventory.validate(inv_answer(e),e)
        extra=copy.deepcopy(e);extra['stable_id']='u::missing'
        checked=alignment.qualify(answer(second=finding('R2')),[spec()],[item()],'unit')
        result=rollup.build([spec()],[e,extra],{'u::L1':inv},{},{'u':checked},{})
        self.assertEqual(result['course']['DEMO.A']['evidence_sufficiency'],'incomplete')


if __name__=='__main__':unittest.main()
