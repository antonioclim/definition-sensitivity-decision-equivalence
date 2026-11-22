"""Exact finite-state reference operations for the R13 research design.

Standard library only. This module reads no files, opens no network connections
and does not import or alter the frozen simulation engine. Fractions describe
the supplied numbers exactly; they do not remove measurement or sampling error.
"""
from fractions import Fraction
from typing import Mapping, Sequence


def rational(value):
    """Accept exact integers/strings/Fractions, reject implicit binary floats."""
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError('Use an exact integer or a rational/decimal string')
    if not isinstance(value, (int, str, Fraction)):
        raise ValueError('Unsupported exact number type')
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError('Invalid finite rational number') from exc


def state_masses(states: Sequence[str], totals: Mapping[str, object]):
    if not states or len(set(states)) != len(states):
        raise ValueError('State identifiers must be nonempty and unique')
    if set(totals) != set(states):
        raise ValueError('State keys must exactly match the declared register')
    weights = {s:rational(totals[s]) for s in states}
    if any(v < 0 for v in weights.values()) or sum(weights.values()) <= 0:
        raise ValueError('State totals must be nonnegative with a positive sum')
    denominator = sum(weights.values())
    return {s:weights[s]/denominator for s in states}


def rate(masses: Mapping[str, object], boundary: Sequence[str]):
    if len(set(boundary)) != len(boundary) or not set(boundary) <= set(masses):
        raise ValueError('Boundary must be a subset without duplicate states')
    p = {s:rational(x) for s,x in masses.items()}
    if any(x < 0 for x in p.values()) or sum(p.values()) != 1:
        raise ValueError('State masses must be a probability distribution')
    return sum((p[s] for s in boundary), Fraction(0))


def semantic_loss(masses, boundary, objective, costs=(1,1)):
    # Validate the distribution and mappings even if an error class is empty.
    rate(masses, boundary)
    rate(masses, objective)
    c_fp, c_fn = map(rational, costs)
    if c_fp < 0 or c_fn < 0:
        raise ValueError('Costs must be nonnegative')
    d, q = set(boundary), set(objective)
    fp = sum((rational(masses[s]) for s in d-q), Fraction(0))
    fn = sum((rational(masses[s]) for s in q-d), Fraction(0))
    return {'false_inclusion_mass':fp, 'false_exclusion_mass':fn,
            'semantic_loss':c_fp*fp+c_fn*fn}


def _scores_and_priority(scores, priority):
    if not scores:
        raise ValueError('At least one eligible unit is required')
    if len(priority) != len(scores) or len(set(priority)) != len(priority) or set(priority) != set(scores):
        raise ValueError('Priority must be a permutation of the common unit universe')
    return {g:rational(x) for g,x in scores.items()}, {g:i for i,g in enumerate(priority)}


def select(scores, rule, priority):
    """A fixed priority is shared by all definitions and the objective."""
    p, order = _scores_and_priority(scores, priority)
    kind = rule['kind']
    if kind == 'threshold':
        tau = rational(rule['threshold'])
        predicates = {'lt':lambda x:x<tau,'le':lambda x:x<=tau,
                      'gt':lambda x:x>tau,'ge':lambda x:x>=tau}
        if rule['operator'] not in predicates:
            raise ValueError('Threshold operator must be explicit')
        return frozenset(g for g,x in p.items() if predicates[rule['operator']](x))
    if kind == 'rank':
        k = rule['k']
        if isinstance(k,bool) or not isinstance(k,int) or not 0 <= k <= len(p):
            raise ValueError('k must be an integer from zero to the universe size')
        direction = rule['direction']
        if direction not in {'highest','lowest'}:
            raise ValueError('Rank direction must be highest or lowest')
        sign = -1 if direction == 'highest' else 1
        ranking = sorted(p,key=lambda g:(sign*p[g],order[g]))
        return frozenset(ranking[:k])
    raise ValueError('Unsupported decision rule')


def action_loss(selected, reference, universe, costs=(1,1)):
    a, b, u = set(selected),set(reference),set(universe)
    if not u or not a <= u or not b <= u:
        raise ValueError('Action sets must use the same nonempty universe')
    c_fp,c_fn = map(rational,costs)
    if c_fp < 0 or c_fn < 0:
        raise ValueError('Costs must be nonnegative')
    fp,fn = len(a-b),len(b-a)
    loss = c_fp*fp+c_fn*fn
    return {'false_selection_count':fp,'missed_reference_count':fn,
            'action_loss_count_scale':loss,'action_loss_per_unit':loss/len(u),
            'selected_count':len(a),'reference_count':len(b)}


def compare_sets(left, right, universe, rank_k=None):
    """Report churn only when a positive rank cardinality is explicitly declared."""
    a,b,u = set(left),set(right),set(universe)
    if not u or not a <= u or not b <= u:
        raise ValueError('Compared sets must use the same nonempty universe')
    union = a|b
    if rank_k is not None and (isinstance(rank_k,bool) or not isinstance(rank_k,int) or not 0 <= rank_k <= len(u)):
        raise ValueError('Declared rank cardinality must be a valid integer')
    equal_k = rank_k is not None and rank_k>0 and len(a)==len(b)==rank_k
    if rank_k is not None and (len(a)!=rank_k or len(b)!=rank_k):
        raise ValueError('Rank sets must have the declared cardinality')
    return {'equal_sets':a==b,'intersection_count':len(a&b),'union_count':len(union),
            'symmetric_difference_count':len(a^b),
            'jaccard':Fraction(len(a&b),len(union)) if union else Fraction(1),
            'jaccard_status':'defined_nonempty_union' if union else 'both_empty_convention_one',
            'normalised_symmetric_difference':Fraction(len(a^b),len(u)),
            'rank_churn':Fraction(len(a^b),2*len(a)) if equal_k else None,
            'rank_churn_status':'defined_equal_positive_rank_size' if equal_k else 'not_applicable_to_rule_or_zero_k'}


def interval_membership(intervals, k, direction, tie_policy='all_admissible', priority=None):
    """Exact membership for a Cartesian product of closed score intervals.

    For a constrained joint set, these are certificates from its rectangular
    envelope: do not label all possible members attainable in the joint set.
    All-admissible ties describe marginal membership for one score vector.
    """
    if not intervals or isinstance(k,bool) or not isinstance(k,int) or not 0<=k<=len(intervals):
        raise ValueError('Nonempty universe and valid integer k required')
    box = {g:tuple(map(rational,pair)) for g,pair in intervals.items()}
    if any(len(pair)!=2 or pair[0]>pair[1] for pair in box.values()):
        raise ValueError('Each closed interval requires lower <= upper')
    if direction not in {'highest','lowest'} or tie_policy not in {'all_admissible','fixed_priority'}:
        raise ValueError('Unknown direction or tie policy')
    order=None
    if tie_policy=='fixed_priority':
        _,order=_scores_and_priority({g:p[0] for g,p in box.items()},priority or [])
    if k==0:return {'guaranteed':frozenset(),'possible':frozenset(),'excluded':frozenset(box)}
    guaranteed,possible=set(),set()
    for g,(lo,hi) in box.items():
        worst=best=0
        for h,(lh,uh) in box.items():
            if h==g:continue
            if direction=='highest':
                # g at its low endpoint is worst; at its high endpoint is best.
                strict_worst,eq_worst=uh>lo,uh==lo
                strict_best,eq_best=lh>hi,lh==hi
            else:
                strict_worst,eq_worst=lh<hi,lh==hi
                strict_best,eq_best=uh<lo,uh==lo
            if tie_policy=='all_admissible':
                worst+=strict_worst or eq_worst
                best+=strict_best
            else:
                ahead=order[h]<order[g]
                worst+=strict_worst or (eq_worst and ahead)
                best+=strict_best or (eq_best and ahead)
        if worst<=k-1:guaranteed.add(g)
        if best<=k-1:possible.add(g)
    return {'guaranteed':frozenset(guaranteed),'possible':frozenset(possible),
            'excluded':frozenset(set(box)-possible)}


def unresolved_rate_interval(positive_known, known_denominator, unresolved_total):
    """Envelope when every unresolved weight may be inside or outside a boundary.

    The boundary is a nonempty proper subset of the state register. The caller
    must justify that both allocations are allowed; no coupled-country or
    multi-definition feasibility is inferred. Missing denominator is not zero.
    """
    p,d,m=map(rational,(positive_known,known_denominator,unresolved_total))
    if not 0<=p<=d or m<0 or d+m<=0:
        raise ValueError('Require 0 <= known positives <= known denominator and a positive total')
    return p/(d+m),(p+m)/(d+m)


def threshold_membership(intervals, threshold, operator='lt'):
    """Single-coordinate threshold classes from closed attained intervals.

    For outer bounds, possible/ambiguous are envelopes, not attained claims.
    """
    tau=rational(threshold)
    predicates={'lt':lambda x:x<tau,'le':lambda x:x<=tau,
                'gt':lambda x:x>tau,'ge':lambda x:x>=tau}
    if operator not in predicates or not intervals:
        raise ValueError('Explicit supported operator and nonempty intervals required')
    guaranteed,possible=set(),set()
    for g,raw in intervals.items():
        pair=tuple(map(rational,raw))
        if len(pair)!=2 or pair[0]>pair[1]:raise ValueError('Each closed interval requires lower <= upper')
        flags=[predicates[operator](x) for x in pair]
        if all(flags):guaranteed.add(g)
        if any(flags):possible.add(g)
    return {'guaranteed':frozenset(guaranteed),'possible':frozenset(possible),
            'excluded':frozenset(set(intervals)-possible)}
