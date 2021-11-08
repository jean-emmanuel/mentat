from .base import RouteBase

class A(RouteBase):

    def __init__(self):

        RouteBase.__init__(self, 'A')

    def route(self, protocol, port, address, args):

        RouteBase.route(self, protocol, port, address, args)

        # print('route A: ', port, address, args)
