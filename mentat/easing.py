"""
Easing functions for parameter animations
"""

from math import sin, pi
from random import random as rand

def lerp(start, end, p):
    """
    Linear interpolation between 2 floats

    **Parameters**
    - `start`: start value
    - `end`: end value
    - `p`: progress between 0.0 and 1.0
    """
    return start + (end - start) * p

def flip(p):
    """
    Flip a function between 0.0 and 1.0
    """
    return 1 - p

def create_easing(ease_in):
    """
    Generate easing functions (in, out & inout) from a single easing function

    **Parameters**
    - `ease_in`:
        easing function that a take a single float parameter between 0.0 and 1.0
        and returns the eased value between 0.0 and 1.0
    """

    def ease_out(p):
        return flip(ease_in(flip(p)))

    def ease_in_out(p):
        if p < 0.5:
            return ease_in(2 * p) * 0.5
        else:
            return ease_out(2 * (p - 0.5)) * 0.5 + 0.5
        # return lerp(ease_in(p), ease_out(p), p)

    def mirror_in(p):
        if p <= 0.5:
            return ease_in(2 * p)
        else:
            return ease_in(flip(2 * (p - 0.5)))

    def mirror_out(p):
        if p <= 0.5:
            return ease_out(2 * p)
        else:
            return ease_out(flip(2 * (p - 0.5)))

    def mirror_inout(p):
        if p <= 0.5:
            return ease_in_out(2 * p)
        else:
            return ease_in_out(flip(2 * (p - 0.5)))



    easings = {
        'in': ease_in,
        'out': ease_out,
        'inout': ease_in_out,
        'mirror': mirror_in,
        'mirror-in': mirror_in,
        'mirror-out': mirror_out,
        'mirror-inout': mirror_inout
        }

    def ease(start, end, p, mode='in'):

        return lerp(start, end, easings[mode](p))

    return ease



EASING_FUNCTIONS = {
    'linear':      create_easing(lambda p: p),
    'sine':        create_easing(lambda p: sin((p - 1) * pi / 2) + 1),
    'quadratic':   create_easing(lambda p: p * p),
    'cubic':       create_easing(lambda p: p * p * p),
    'quartic':     create_easing(lambda p: p * p * p * p),
    'quintic':     create_easing(lambda p: p * p * p * p * p),
    'exponential': create_easing(lambda p: 0 if p == 0 else pow(2, 10 * (p - 1))),
    'random':      create_easing(lambda p: p if p in (0, 1) else rand()),
    'elastic':     create_easing(lambda p: sin(13 * pi / 2 * p) * pow(2, 10 * (p - 1)))
}



def main():
    """
    Simple test (print easing values)
    """
    for name, interp in EASING_FUNCTIONS.items():
        for mode in ['in', 'out', 'inout', 'mirror-in', 'mirror-out', 'mirror-inout']:
            points = ',\t'.join([f'{interp(0, 10, x / 10, mode):.1f}' for x in range(11)])
            print(f'{name} {mode}\n{points}')

if __name__ == '__main__':
    main()
