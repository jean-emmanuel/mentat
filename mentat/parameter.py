import logging
from inspect import signature

from .easing import EASING_FUNCTIONS

class Parameter():

    def __init__(self, name, address, types, static_args=None, default=None, filter=None, transform=None, **metadata):
        """
        Parameter(name, address, types, static_args=[], default=None, transform=None, **metadata)

        Parameter constructor.

        **Parameters**

        - `name`: name of parameter
        - `address`: osc address of parameter. Can be `None` if the parameter should not send any message.
        - `types`: osc typetags string, one letter per value, including static values
        - `static_args`: list of static values before the ones that can be modified
        - `default`: default value
        - `transform`: transform function
        - `metadata`: extra keyword arguments will be storde in parameter.metadata (dict)
        """
        self.logger = logging.getLogger(__name__).getChild(name)

        if '*' in name or '[' in name:
            self.logger.critical('characters "*" and "[" are forbidden in parameter name')

        if static_args is None:
            static_args = []

        self.name = name
        self.address = address
        self.types = types
        self.args = [None] * len(types)
        for i in range(len(static_args)):
            self.args[i] = static_args[i]
        self.n_args = len(types) - len(static_args)

        if self.n_args < 0:
            self.logger.critical('incoherent values for types and static_args arguments')

        self.animate_running = False
        self.animate_start = 0
        self.animate_duration = 0
        self.animate_from = 0
        self.animate_to = 0
        self.animate_loop = False

        self.easing_function = None
        self.easing_mode = 'in'

        self.default = default
        self.transform = transform
        self.metadata = metadata

        self.dirty = False
        self.dirty_timestamp = 0
        self.last_sent = None

    def get(self):
        """
        get()

        Get parameter value.

        **Return**

        List of n values, where n is the number of
        values specified in constructor's types option
        """

        val = self.args[-self.n_args:]

        return val[0] if len(val) == 1 else val


    def set(self, *args):
        """
        set(*args)

        Set parameter value.

        **Parameters**

        - `*args`:
            n values, where n is the number of
            values specified in constructor's types option

        **Return**

        `True` is the new value differs from the old one, `False` otherwise
        """

        if len(args) != self.n_args:
            self.logger.error('wrong number of arguments for %s (%s). %i expected, %i provided' % (self.name, self.address, self.n_args, len(args)))
            return False

        changed = False

        if self.transform:
            args = self.transform(*args)

        for i in range(self.n_args):
            value = self.cast(args[i], self.types[i - self.n_args])
            if value != self.args[i - self.n_args]:
                self.args[i - self.n_args] = value
                changed = True

        return changed


    def set_last_sent(self):
        """
        Keep a copy of last sent value to check if we should send a message.
        """
        self.last_sent = self.get()

    def should_send(self):
        """
        Compare last send value ot current value.
        """
        return self.last_sent != self.get()

    cast_functions = {
        'i': lambda arg: int(round(arg)) if type(arg) == float else int(arg),
        'h': lambda arg: int(round(arg)) if type(arg) == float else int(arg),
        'f': lambda arg: float(arg),
        'd': lambda arg: float(arg),
        't': lambda arg: float(arg),
        's': lambda arg: str(arg),
        'S': lambda arg: str(arg),
        'c': lambda arg: str(arg),
        'T': lambda arg: True,
        'F': lambda arg: False,
        'm': lambda arg: arg,
        'N': lambda arg: arg,
        'I': lambda arg: arg,
        'b': lambda arg: arg,
    }

    def cast(self, arg, arg_type):
        """
        cast(arg, arg_type)

        Cast value to given type.

        **Parameters**

        - `arg`: input value
        - `arg_type`: osc typetag letter

        **Return**

        Casted value
        """

        if arg_type in self.cast_functions:
            try:
                return self.cast_functions[arg_type](arg)
            except:
                self.logger.debug('cannot cast value %s to type "%s", fallback to %s' % (arg, arg_type, 0))
                return self.cast_functions[arg_type](0)
        else:
            return arg

    def get_message_args(self):
        """
        get_message_args()

        Format typetags and args for liblo.send()

        **Return**
        List of (typetag, value) tuples
        """
        return [
            (self.types[i], self.args[i]) if self.types[i] in self.cast_functions else self.args[i]
            for i in range(len(self.args))
        ]

    def start_animation(self, engine, start, end, duration, mode='beats', easing='linear', loop=False):

        easing_name, _, easing_mode = easing.partition('-')

        if not easing_name in EASING_FUNCTIONS:
            self.logger.error('unknown easing "%s", falling back to "linear"' % easing)
            easing = 'linear'

        self.animate_from = start if start is not None else self.get()
        self.animate_to = end if end is not None else self.get()
        self.animate_start = engine.current_time
        self.animate_duration = duration * 1000000000
        self.animate_loop = loop

        self.easing_function = EASING_FUNCTIONS[easing_name]
        self.easing_mode = easing_mode if easing_mode in ['in', 'out', 'inout', 'mirror', 'mirror-in', 'mirror-out', 'mirror-inout'] else 'in'

        if type(self.animate_from) is not list:
            self.animate_from = [self.animate_from]
        if type(self.animate_to) is not list:
            self.animate_to = [self.animate_to]

        if mode[0] == 'b':
            self.animate_duration = self.animate_duration * 60. / engine.tempo
        elif mode[0] != 's':
            self.logger.error('start_animation: unrecognized mode "%s"' % mode)
            return

        if len(self.animate_from) != self.n_args:
            self.logger.error('start_animation: wrong number of values for argument "from" (%i expected, %i provided)' % (self.n_args, len(self.animate_from)))
        elif len(self.animate_from) != self.n_args:
            self.logger.error('start_animation: wrong number of values for argument "to" (%i expected, %i provided)' % (self.n_args, len(self.animate_from)))
        else:
            self.animate_running = True

    def stop_animation(self):
        self.animate_running = False

    def update_animation(self, current_time):

        t = current_time - self.animate_start
        if t >= self.animate_duration:
            if self.animate_loop:
                self.animate_start += self.animate_duration
            else:
                t = self.animate_duration
                self.stop_animation()

        progress = t / self.animate_duration if self.animate_duration > 0 else 1.0
        value = [self.easing_function(self.animate_from[i], self.animate_to[i], progress, self.easing_mode) for i in range(self.n_args)]

        return self.set(*value)

class Mapping():
    """
    A mapping is a value binding between two or more parameters
    """
    def __init__(self, src, dest, transform, condition):


        if type(src) != list:
            self.src = [(src,)] if type(src) != tuple else [src]
        else:
            self.src = [(x,) if type(x) is not tuple else x for x in src]


        if type(dest) != list:
            self.dest = [(dest,)] if type(dest) != tuple else [dest]
        else:
            self.dest = [(x,) if type(x) is not list else x for x in dest]

        self.n_args = len(self.dest)

        self.transform = transform
        self.condition = condition
        self.locked = False

    def match(self, param, ignore_condition=False):
        """
        Check if provided parameter should trigger this mapping
        """

        m = False
        if type(param) == str :
            for s in self.src:
                if len(s) == 1 and s[0] == param:
                    m = True
        else:
            for s in self.src:
                if len(s) == len(param):
                    for i in range(len(s)):
                        if s[i] != param[i]:
                            break
                    else:
                        m = True

        if m and not ignore_condition and self.condition is not None:
            if not self.condition():
                return False
        return m

    def lock(self):
        """
        Simple lock to prevent feedback loop
        """
        if self.locked:
            return False
        else:
            self.locked = True
            return True

    def unlock(self):
        self.locked = False


    def __lt__(self, other):
        """
        Custom comparison operator for sorting.
        Basically, if A depends on B's results, B should be resolved first.
        """
        e = 0

        # how much does self depend on other
        for param in other.dest:
            if self.match(param, True):
                e += 1

        # how much does other depend on self
        for param in self.dest:
            if other.match(param, True):
                e -= 1

        # in case of equality, resolve mapping with fewer src args first
        if e == 0 and len(self.src) > len(other.src):
            e += 1

        return e <= 0

class MetaParameter(Parameter):

    def __init__(self, name, parameters, getter, setter, module):

        self.module = module

        if type(parameters) != list:
            self.parameters = [(parameters,)] if type(parameters) != tuple else [parameters]
        else:
            self.parameters = [(x,) if type(x) is not tuple else x for x in parameters]

        self.getter = getter
        self.setter = setter
        self.lock = False

        types = '*' * len(signature(setter).parameters)

        super().__init__(name, address='', types=types)

    def match(self, param):
        """
        Check if provided parameter should trigger this mapping
        """
        if type(param) == str :
            for s in self.parameters:
                if len(s) == 1 and s[0] == param:
                    return True
        else:
            for s in self.parameters:
                if len(s) == len(param):
                    for i in range(len(s)):
                        if s[i] != param[i]:
                            break
                    else:
                        return True

        return False

    def set(self, *args):
        """
        Call user-defined setter function

        **Parameters**

        - `*args`: values for the setter function

        **Return**

        `True` if the value changed, `False` otherwise.
        """

        if len(args) != self.n_args:
            self.logger.error('wrong number of arguments for %s. %i expected, %i provided' % (self.name, self.n_args, len(args)))
            return False

        self.lock = True
        self.setter(*args)
        self.lock = False

        return self.update()

    def update(self):
        """
        Call user-defined getter function to determine the meta parameter's own value

        **Return**

        `True` if the value changed, `False` otherwise.
        """

        if self.lock:
            return False

        # get current value of linked parameters
        values = [self.module.get(*x) for x in self.parameters]
        # compute meta parameter value
        value = self.getter(*values)

        # update internal value and check if it changed
        if type(value) is list:
            return Parameter.set(self, *value)
        else:
            return Parameter.set(self, value)
