from cement.staged_classification import stages, route


def test_title_and_contents_separate_from_body():
    ps=[{'page':1,'text':'1\nVirtual Cement Laboratory\nVersion 9 User Guide\nAuthor\nresearch results'},
        {'page':3,'text':'CONTENTS\nInstallation .... 4\nRunning .... 7\nResults .... 10'}]
    ss=stages(ps,'pdf')
    assert [s['stage'] for s in ss]==['title','contents','body']
    assert ss[0]['text'].endswith('User Guide') and 'Author' not in ss[0]['text']
    assert ss[1]['source_pages']==[3]
    cover=stages([{'page':1,'text':'Company\nPortrait\nStrategy\nBusiness\nManagement\nOther\nTopics\nMore\nSustainability Report\n2021'}],'pdf')
    assert cover[0]['text']=='Sustainability Report'


def test_cascade_early_exit_escalation_and_abstain():
    def score(a,b):return {'scores':{'manual':a,'research':b},'seconds':1}
    row={'stages':[{'stage':'title','embedding':score(.9,.7),'reranker':score(-1,-2)},
                   {'stage':'contents','embedding':score(.8,.79),'reranker':score(3,1)},
                   {'stage':'body','embedding':score(.95,.5),'reranker':score(5,1)}]}
    d=route(row,.85,.1,0,1)
    assert d['stage']=='title' and d['reranker_calls']==0
    d=route(row,.96,.1,0,1)
    assert d['stage']=='body' and d['reranker_calls']==1
    assert 'title:reranker' not in d['trace'] and 'contents:reranker' not in d['trace']
    d=route(row,1,.5,6,5)
    assert d['prediction'] is None and d['method']=='abstain'


def test_content_only_input_and_missing_reranker_on_title():
    ss=stages([{'page':1,'text':'x'*300}],'pdf')
    assert [s['stage'] for s in ss]==['body']
    row={'stages':[{'stage':'title','embedding':{'scores':{'manual':.5,'research':.49},'seconds':1}},
                   {'stage':'body','embedding':{'scores':{'manual':.5,'research':.49},'seconds':1},
                    'reranker':{'scores':{'manual':3,'research':0},'seconds':1}}]}
    d=route(row,.8,.02,0,1)
    assert d['prediction']=='manual' and d['reranker_calls']==1
    assert d['trace']==['title:embedding','body:embedding','body:reranker']
