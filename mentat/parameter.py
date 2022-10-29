import logging
from inspect import signature

from .utils import *
from .easing import EASING_FUNCTIONS

class Parameter():

    @public_method
    def __init__(self, name, address, types, static_args=[], default=None):
        """
        Parameter(name, address, types, static_args=[], default=None)

        Parameter constructor.

        **Parameters**

        - `name`: name of parameter
        - `address`: osc address of parameter. Can be `None` if the parameter should not send any message.
        - `types`: osc typetags string, one letter per value, including static values
        - `static_args`: list of static values before the ones that can be modified
        - `default`: default value
        """
        if '*' in name or '[' in name:
            self.logger.error('characters "*" and "[" are forbidden in parameter name')
            raise Exception

        self.logger = logging.getLogger(__name__).getChild(name)
        self.name = name
        self.address = address
        self.types = types
        self.args = [None] * len(types)
        for i in range(len(static_args)):
            self.args[i] = static_args[i]
        self.n_args = len(types) - len(static_args)

        self.animate_running = False
        self.animate_start = 0
        self.animate_duration = 0
        self.animate_from = 0
        self.animate_to = 0
        self.animate_loop = False

        self.easing_function = None
        self.easing_mode = 'in'

        self.default = default

        self.dirty = False
        self.last_sent = None

    @public_method
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


    @public_method
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

    def cast(self, arg, arg_type):
        """
        cast(arg, arg_type)

        Cast value to given type.

        **Parameters**

        - `arg`: input value
        - `arg_type`: osc typetag letter (supported: 'ifsTF')

        **Return**

        Casted value
        """

        if arg_type == 'i':
            return int(round(arg)) if type(arg) == float else int(arg)
        elif arg_type == 'f':
            return float(arg)
        elif arg_type == 's':
            return str(arg)
        elif arg_type == 'T':
            return True
        elif arg_type == 'F':
            return False
        else:
            return arg

    def start_animation(self, engine, start, end, duration, mode='beats', easing='linear', loop=False):

        easing_name, _, easing_mode = easing.partition('-')

        if not easing_name in EASING_FUNCTIONS:
            self.logger.error('unknown easing "%s", falling back to "linear"' % easing)
            easing = 'linear'

        self.animate_from = start if start is not None else self.get()
        self.animate_to = end
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


        value = [self.easing_function(self.animate_from[i], self.animate_to[i], t / self.animate_duration, self.easing_mode) for i in range(self.n_args)]

        return self.set(*value)


class MetaParameter(Parameter):

    def __init__(self, name, parameters, getter, setter, module):

        self.module = module
        self.parameters = [[x] if type(x) is not list else x for x in parameters]
        self.getter = getter
        self.setter = setter
        self.lock = False

        types = '*' * len(signature(setter).parameters)

        super().__init__(name, address='', types=types)

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

        value = self.get()

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
