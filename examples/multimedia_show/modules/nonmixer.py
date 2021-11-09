from mentat.module import Module

class Strip(Module):

    def __init__(self, *args, **kwargs):

        Module.__init__(self, *args, **kwargs)

class NonMixer(Module):

    def __init__(self, *args, **kwargs):

        Module.__init__(self, *args, **kwargs)

        self.signals = {}

    def initialize(self, *args, **kwargs):

        Module.initialize(self, *args, **kwargs)

        self.send('/non/hello', self.engine.osc_server.get_url(), '', '', self.engine.name)
        self.send('/signal/list')

    def route(self, address, args):

        if address == '/reply' and args[0] == '/signal/list':

            if len(args) > 1:

                path = args[1].split('/')

                if path[1] == 'strip':

                    strip_name = path[2]

                    if strip_name not in self.submodules:

                        self.add_submodule(Strip(strip_name))

                    if path[-1] == 'unscaled':

                        parameter_name = '/'.join(path[3:-1])
                        self.submodules[strip_name].add_parameter(parameter_name, args[1], 'f')
            else:

                # we're done ! (last messagage: only 1 arg)
                print(self.submodules)

            print(address, args)
