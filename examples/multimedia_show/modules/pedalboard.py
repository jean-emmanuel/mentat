from mentat.module import Module

class Pedalboard(Module):

    def __init__(self, *args, **kwargs):

        Module.__init__(self, *args, **kwargs)

        self.add_event_callback('parameter_changed', self.parameter_changed)

    def parameter_changed(self, module_path, name, values):

        self.logger.info('parameter changed: %s %s %s' % (module_path, name, values))

    def route(self, address, args):

        module_path = address.split('/')[1:]

        self.engine.modules[module_path[0]].set(*module_path[:1], *args)
