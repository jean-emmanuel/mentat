from .easing import EASING_FUNCTIONS
import time
class Parameter():

    def __init__(self, name, address, types, static_args=[]):
        """
        Parameter(name, address, types)
        Parameter(name, address, types, static_args)

        Parameter constructor.

        :param name: name of parameter
        :param address: osc address of parameter
        :param types: osc typetags string, one letter per value, including static values
        :param static_args: list of static values before the ones that can be modified
        """

        self.name = name
        self.address = address
        self.types = types
        self.args = [0] * len(types)
        for i in range(len(static_args)):
            self.args[i] = static_args[i]
        self.n_args = len(types) - len(static_args)

        self.animate_running = False
        self.animate_start = 0
        self.animate_duration = 0
        self.animate_from = 0
        self.animate_to = 0
        self.animate_easing = None

    def get(self):
        """
        get()

        Get parameter value.

        :return:
            list of n values, where n is the number of
            values specified in constructor's types option
        """

        return self.args[-self.n_args:]

    def set(self, *args):
        """
        set(*args)

        Set parameter value.

        :param *args:
            n values, where n is the number of
            values specified in constructor's types option

        :return:
            True is the new value differs from the old one, False otherwise
        """
        if len(args) != self.n_args:
            # LOGGER ERROR
            raise TypeError('wrong number of arguments for %s (%s)' % (name, address))

        for i in range(self.n_args):
            value = self.cast(args[i], self.types[i - self.n_args])
            if value != self.args[i - self.n_args]:
                self.args[i - self.n_args] = value
                return True
            else:
                return False

    def cast(self, arg, type):
        """
        cast(arg, type)

        Cast value to given type.

        :param arg: input value
        :param type: osc typetag letter (supported: 'ifsTF')

        :return:
            casted value
        """

        if type == 'i':
            return int(arg)
        elif type == 'f':
            return float(arg)
        elif type == 's':
            return str(arg)
        elif type == 'T':
            return True
        elif type == 'F':
            return False
        else:
            return arg

    def start_animation(self, current_time, start, end, duration, easing='linear'):

        if not easing in EASING_FUNCTIONS:
            LOGGER.error('unknown easing "%s", falling back to "linear"' % easing)
            easing = 'linear'

        self.animate_from = start if start is not None else self.get()
        self.animate_to = end
        if type(self.animate_from) is not list:
            self.animate_from = [self.animate_from]
        if type(self.animate_to) is not list:
            self.animate_to = [self.animate_to]
        self.animate_start = current_time
        self.animate_duration = duration * 1000000000
        self.animate_easing = [
            EASING_FUNCTIONS[easing](
                start=self.animate_from[i],
                end=self.animate_to[i],
                duration=self.animate_duration
            )
            for i in range(self.n_args)
        ]

        if len(self.animate_from) != self.n_args:
            LOGGER.error('wrong number of values for argument "from" (expected %i)' % self.n_args)
        elif len(self.animate_from) != self.n_args:
            LOGGER.error('wrong number of values for argument "to" (expected %i)' % self.n_args)
        else:
            self.animate_running = True

    def stop_animation(self):
        self.animate_running = False

    def update_animation(self, current_time):

        t = current_time - self.animate_start
        if t >= self.animate_duration:
            t = self.animate_duration
            self.stop_animation()

        value = [self.animate_easing[i].ease(t) for i in range(self.n_args)]

        return self.set(*value)
