from mentat.module import Module

class Pedalboard(Module):

    def __init__(self, *args, **kwargs):

        Module.__init__(self, *args, **kwargs)

        self.add_event_callback('parameter_changed', self.parameter_changed)

    def parameter_changed(self, module, name, values):

        self.logger.info('parameter changed: %s %s %s' % (module.name, name, values))
