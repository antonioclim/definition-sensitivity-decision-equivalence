"""Construct the R13 point-comparison output schema."""
from pathlib import Path
import json
from build_contract_schema import RATIONAL, IDENTIFIER, IDS, SHA, obj
ROOT=Path(__file__).resolve().parent
COUNT={'type':'integer','minimum':0}
def mapping(v):return {'type':'object','additionalProperties':v}
semantic=obj({'false_inclusion_mass':RATIONAL,'false_exclusion_mass':RATIONAL,'semantic_loss':RATIONAL})
loss=obj({'false_selection_count':COUNT,'missed_reference_count':COUNT,'action_loss_count_scale':RATIONAL,
    'action_loss_per_unit':RATIONAL,'selected_count':COUNT,'reference_count':COUNT})
comparison_props={'equal_sets':{'type':'boolean'},'intersection_count':COUNT,'union_count':COUNT,
    'symmetric_difference_count':COUNT,'jaccard':RATIONAL,
    'jaccard_status':{'enum':['defined_nonempty_union','both_empty_convention_one']},
    'normalised_symmetric_difference':RATIONAL,'rank_churn':{'oneOf':[RATIONAL,{'type':'null'}]},
    'rank_churn_status':{'enum':['defined_equal_positive_rank_size','not_applicable_to_rule_or_zero_k']}}
rule=obj({'selected_sets':mapping(IDS),
    'pairwise_definition_comparisons':{'type':'array','items':obj({'left':IDENTIFIER,'right':IDENTIFIER,**comparison_props})},
    'objective_comparisons':mapping(obj(comparison_props)),'objective_losses':mapping(mapping(loss))})
props={'schema_version':{'const':'R13.1'},'dataset_kind':{'enum':['TOY','FAT','OA']},
    'input_status':{'enum':['synthetic_fixture','real_extension_input']},
    'release_status':{'const':'working_only_not_release_approval'},'unit_count':{'type':'integer','minimum':1},
    'unit_ids':{**IDS,'minItems':1},'mixture_weighting':{'const':'equal_eligible_units'},
    'rates':mapping(mapping(RATIONAL)),'mixture_masses':mapping(RATIONAL),
    'semantic':mapping(mapping(semantic)),'rules':mapping(rule),'scope':{'type':'string'},
    'identities':obj({'input_sha256':SHA,'core_sha256':SHA,'executor_sha256':SHA})}
schema={'$schema':'https://json-schema.org/draft/2020-12/schema','title':'R13 working point-comparison output',
    **obj(props,[k for k in props if k!='identities'])}
(ROOT/'R13_STATE_OUTPUT.schema.json').write_text(json.dumps(schema,indent=2)+'\n')
print('Wrote the output schema. Cross-field mathematical validity is checked separately.')
