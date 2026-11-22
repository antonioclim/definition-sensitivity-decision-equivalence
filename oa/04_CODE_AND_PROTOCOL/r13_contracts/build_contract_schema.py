"""Build the R13 normalised-state interchange schema and a wholly synthetic fixture."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parent
RATIONAL={"type":"string","pattern":r"^-?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$|^-?[0-9]+/[1-9][0-9]*$"}
IDENTIFIER={"type":"string","minLength":1,"maxLength":160}
IDS={"type":"array","items":IDENTIFIER,"uniqueItems":True}
SHA={"type":"string","pattern":"^[a-f0-9]{64}$"}
def obj(properties,required=None):
    return {"type":"object","properties":properties,"required":list(properties) if required is None else required,"additionalProperties":False}

unit=obj({"id":IDENTIFIER,"state_totals":{"type":"object","additionalProperties":RATIONAL,"minProperties":1},
    "known_denominator":RATIONAL,"unresolved_total":{"oneOf":[RATIONAL,{"type":"null"}]},
    "unresolved_status":{"enum":["known_nonnegative_total","not_identifiable"]}})
rank=obj({"id":IDENTIFIER,"kind":{"const":"rank"},"direction":{"enum":["highest","lowest"]},"k":{"type":"integer","minimum":1}})
threshold=obj({"id":IDENTIFIER,"kind":{"const":"threshold"},"operator":{"enum":["lt","le","gt","ge"]},"threshold":RATIONAL})
schema={"$schema":"https://json-schema.org/draft/2020-12/schema","title":"R13 normalised finite-state comparison input",
    "description":"A post-adapter contract, not proof that a source extraction or eligibility decision is correct.",
    **obj({"schema_version":{"const":"R13.1"},"dataset_kind":{"enum":["TOY","FAT","OA"]},
    "input_status":{"enum":["synthetic_fixture","real_extension_input"]},
    "provenance":obj({"source_label":IDENTIFIER,"source_sha256":SHA,"adapter_status":{"enum":["synthetic_construction","independently_reconciled"]}}),
    "states":{**IDS,"minItems":1},"units":{"type":"array","minItems":1,"items":unit},
    "boundaries":{"type":"array","minItems":2,"items":obj({"id":IDENTIFIER,"states":IDS})},
    "nested_boundaries":{"const":True},"objective":obj({"id":IDENTIFIER,"states":IDS}),
    "priority":{**IDS,"minItems":1},"rules":{"type":"array","minItems":1,"items":{"oneOf":[rank,threshold]}},
    "cost_profiles":{"type":"array","minItems":1,"items":obj({"id":IDENTIFIER,"false_positive":RATIONAL,"false_negative":RATIONAL})},
    "action_cost_profiles_by_rule":{"type":"object","additionalProperties":{**IDS,"minItems":1}},
    "mixture_weighting":{"const":"equal_eligible_units"},"primary_missing_policy":{"const":"complete_known_states"}})}

def write(name,value):
    (ROOT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    import hashlib
    write('R13_STATE_INPUT.schema.json',schema)
    states=['manual','standard','platform','specialised','integrated']
    rows={
        'a':[60,10,10,10,10],
        'b':[50,30,5,5,10],
        'c':[40,10,20,20,10],
        'd':[20,30,10,20,20],
        'e':[30,45,5,10,10],
        'f':[10,10,20,30,30],
        'g':[55,20,5,10,10],
        'h':[40,20,10,10,20]}
    source=json.dumps(rows,sort_keys=True,separators=(',',':')).encode()
    (ROOT/'R13_SYNTHETIC_SOURCE_ROWS.json').write_bytes(source)
    units=[{'id':g,'state_totals':dict(zip(states,map(str,weights))),
        'known_denominator':'100','unresolved_total':'0','unresolved_status':'known_nonnegative_total'} for g,weights in rows.items()]
    fixture={'schema_version':'R13.1','dataset_kind':'TOY','input_status':'synthetic_fixture',
        'provenance':{'source_label':'Eight deliberately constructed units; no FAT or OpenAlex observations',
            'source_sha256':hashlib.sha256(source).hexdigest(),'adapter_status':'synthetic_construction'},
        'states':states,'units':units,'boundaries':[
            {'id':'narrow','states':['integrated']},
            {'id':'middle','states':['specialised','integrated']},
            {'id':'broad','states':states[1:]}],
        'nested_boundaries':True,'objective':{'id':'platform_or_more','states':states[2:]},
        'priority':list(rows),'rules':[
            {'id':'lowest3','kind':'rank','direction':'lowest','k':3},
            {'id':'highest3','kind':'rank','direction':'highest','k':3},
            {'id':'below025','kind':'threshold','operator':'lt','threshold':'0.25'}],
        'cost_profiles':[
            {'id':'equal','false_positive':'1','false_negative':'1'},
            {'id':'miss_costly','false_positive':'1','false_negative':'2'},
            {'id':'include_costly','false_positive':'2','false_negative':'1'}],
        'action_cost_profiles_by_rule':{'lowest3':['equal'],'highest3':['equal'],
            'below025':['equal','miss_costly','include_costly']},
        'mixture_weighting':'equal_eligible_units','primary_missing_policy':'complete_known_states'}
    write('R13_SYNTHETIC_INPUT.json',fixture)
    print('Wrote the input schema and an explicitly synthetic fixture.')

if __name__=='__main__':main()
