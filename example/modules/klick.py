from mentat.module import Module

class Test(Module):

    def __init__(self, *args, **kwargs):

        Module.__init__(self, *args, **kwargs)

        self.add_parameter('bite', '/klick/simple/set_bite', 'f')


class Klick(Module):

    def __init__(self, *args, **kwargs):

        Module.__init__(self, *args, **kwargs)

        self.add_submodule(Test('test'))

        self.add_parameter('pattern', '/klick/simple/set_pattern', 's')
        self.add_parameter('tempo', '/klick/simple/set_tempo', 'f')

    def start(self):
        self.send('/klick/metro/start')

    def stop(self):
        self.send('/klick/metro/stop')
