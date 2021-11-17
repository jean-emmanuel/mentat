from mentat.module import Module

class SubKlick(Module):

    def __init__(self, *args, **kwargs):

        Module.__init__(self, *args, **kwargs)

        self.add_parameter('thing', '/subklick/simple/set_thing', 'f', default=0)


class Klick(Module):

    def __init__(self, *args, **kwargs):

        Module.__init__(self, *args, **kwargs)

        self.add_submodule(SubKlick('test', parent=self))

        self.add_parameter('pattern', '/klick/simple/set_pattern', 's', default="Xxxx")
        self.add_parameter('tempo', '/klick/simple/set_tempo', 'f', default=120)
        self.add_parameter('some_array', '/klick/simple/xy', 'ff', default=[0,0])

        self.add_condition('tempat', ['tempo', 'pattern', ['test', 'thing']],
            getter = lambda t,p,tt: t > 150 and p != "Xxxx" and tt < 0,
            setter = lambda s: [self.set('tempo', 160 if s else 140),
                               self.set('pattern', 'Xxx' if s else 'Xxxx'),
                               self.set('test', 'thing', -1 if s else 0)]
        )

        self.add_event_callback('condition_changed', self.condition_changed)

    def condition_changed(self, module, name, value):

        if module == self:
            self.logger.info('condition %s changed to %s' % (name, value))

    def start(self):
        self.send('/klick/metro/start')

    def stop(self):
        self.send('/klick/metro/stop')
