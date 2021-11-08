from .base import RouteBase

class B(RouteBase):

    def __init__(self):

        RouteBase.__init__(self, 'B')

    def route(self, protocol, port, address, args):

        RouteBase.route(self, protocol, port, address, args)

        print('route B: ', port, address, args)
