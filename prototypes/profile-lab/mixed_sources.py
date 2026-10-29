"""A language/exam website row is a view of linked independent objects."""
from profile_schema import available
from requirements import resolve_set


def source(state,session,mapping,member,primary,group):
    from application import entry_material
    rule=member.get('source_mapping')
    if not rule or rule.get('record_type')==primary.get('record_type'):
        return primary,None
    if not mapping.get('multi_source') or primary.get('record_type')!='exam' or rule.get('record_type')!='ability':
        return None,'网页行来源类型不支持'
    linked={l['ability_id'] for l in state.get('language_exam_links',[]) if l.get('active') and l['exam_id']==primary['id']}
    options=[entry_material(state,session,e,group) for e in state['entries'] if e['id'] in linked and available(e,session) and not e.get('application_excluded')
             and e['id'] not in session.get('website',{}).get('excluded_entry_ids',[])
             and e.get('record_type')=='ability' and (not rule.get('entry_ids') or e['id'] in rule['entry_ids'])]
    chosen,_,issues=resolve_set(options,rule['requirement'],session.get('group_choices',{}).get(rule['requirement']['group']))
    if issues or len(chosen)!=1 or chosen[0].get('profile_reference_invalid'):return None,'此考试尚无唯一且符合范围的关联语言能力，请先核对关联'
    return chosen[0],None
