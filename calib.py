"""Projected % and the call.

    Form %      = 60% season hit rate + 40% last-5 hit rate over the line (+ NFL matchup nudge)
    Projected % = 75% Form % + 25% Vegas % of the over (a light blend, so lopsided prices pull a bit)

    Green  OVER   58%+
    Yellow LEAN   46-57%  (shown and tracked, not a full call)
    Red    UNDER  45% or less
    STRONG        70%+ over, or 30% or less under
"""
VEGAS_WEIGHT = 0.25
GREEN, YELLOW = 58, 46
STRONG_OVER, STRONG_UNDER = 70, 30
LOW_CONF = {"Anytime TD"}          # priced from Vegas alone, marked low confidence
DROP_HALF = {"Steals", "Blocks"}   # 0.5 lines on these are taken off the board


def project(form, vg):
    if vg is None:
        return form
    return max(1, min(99, round((1 - VEGAS_WEIGHT) * form + VEGAS_WEIGHT * vg)))


def td_chance(vg):
    """Anytime TD: Vegas' yes price with its built-in margin taken out (graded TDs ran ~10% under it)."""
    return max(1, min(99, round((vg or 0) * 0.9)))


def call(proj):
    return "hit" if proj >= GREEN else "lean" if proj >= YELLOW else "miss"


def strong(proj):
    return proj >= STRONG_OVER or proj <= STRONG_UNDER
