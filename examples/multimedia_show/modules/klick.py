from mentat.module import Module

class SubKlick(Module):

    def __init__(self, *args, **kwargs):

        Module.__init__(self, *args, **kwargs)

        self.add_parameter('thing', '/subklick/simple/set_thing', 'f', default=0)
        self.add_parameter('thing2', '/subklick/simple/set_thing2', 'f', default=0)




class Klick(Module):

    def __init__(self, *args, **kwargs):

        Module.__init__(self, *args, **kwargs)

        self.add_submodule(SubKlick('test', parent=self))

        self.add_parameter('pattern', '/klick/simple/set_pattern', 's', default="Xxxx")
        self.add_parameter('tempo', '/klick/simple/set_tempo', 'f', default=120)
        self.add_parameter('some_array', '/klick/simple/xy', 'ff', default=[0,0])

        self.add_meta_parameter('tempo_and_pattern', parameters=['tempo', 'pattern', ['test', 'thing']],
            getter = lambda t,p,tt: t > 150 and p != "Xxxx" and tt < 0,
            setter = lambda s: [self.set('tempo', 160 if s else 140),
                               self.set('pattern', 'Xxx' if s else 'Xxxx'),
                               self.set('test', 'thing', -1 if s else 0)]
        )

        self.add_meta_parameter('things', parameters=[['test', 'thing'], ['test', 'thing2']],
            getter = lambda t,t2: (t + t2) / 2,
            setter = lambda s: [self.set('test', 'thing', s),
                               self.set('test', 'thing2', s)]
        )



        self.add_parameter('position', None, 'fff', default=[0,0,0])

        axis = {0: '_x', 1: '_y', 2: '_z'}
        for index, ax in axis.items():
            def closure(index, ax):

                def setter(val):
                    value = self.get('position')
                    value[index] = val
                    self.set('position', *value, preserve_animation = True)

                self.add_meta_parameter('position' + ax, ['position'],
                    getter = lambda prop: prop[index],
                    setter = setter
                )

            closure(index, ax)

    def start(self):
        self.send('/klick/metro/start')

    def stop(self):
        self.send('/klick/metro/stop')
