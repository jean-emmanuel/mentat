import math

def lerp(start, end, p):
    """
    Linear interpolation between 2 floats

    **Parameters**
    - `start`: start value
    - `end`: end value
    - `p`: progress between 0.0 and 1.0
    """
    return (start + (end - start) * p)

def create_easing(ease_in):
    """
    Generate easing functions (in, out & inout) from a single easing function

    **Parameters**
    - `ease_in`:
        easing function that a take a single float parameter between 0.0 and 1.0
        and returns the eased value between 0.0 and 1.0
    """

    def ease_out(p):
        return 1 - ease_in(1 - p)

    def ease_in_out(p):
        return lerp(ease_in(p), ease_out(p), p)

    e = {'in': ease_in, 'out': ease_out, 'inout': ease_in_out}

    def ease(start, end, p, mode='in'):

        return lerp(start, end, e[mode](p))

    return ease



EASING_FUNCTIONS = {
    'linear':      create_easing(lambda p: p),
    'quadratic':   create_easing(lambda p: p * p),
    'cubic':       create_easing(lambda p: p * p * p),
    'exponential': create_easing(lambda p: 0 if p == 0 else math.pow(2, 10 * (p - 1))),
}


if __name__ == '__main__':
    for name, interp in EASING_FUNCTIONS.items():
        for mode in ['in', 'out', 'inout']:
            print(name, mode, '\n', ',\t'.join(['%.1f' % interp(0, -10, x / 10, mode) for x in range(11)]))
