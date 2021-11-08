from mentat.route import Route
from modules import *

class RouteBase(Route):

    def route(self, protocol, port, address, args):

        print('route base: ', port, address, args)

        Route.route(self, protocol, port, address, args)

        if port == 'kbd':
            print('midi from kbd: ', address, args)
            mon.send(address, *args)

        if address == '/save':
            klick1.save('test')


        if address == '/load':
            klick1.load('test')

        if address == '/scene':
            # klick1.set('tempo', 12)
            # klick1.set('pattern', 'xXXx')
            # self.start_scene('test', self.scene)
            # self.stop_scene('*')
            klick1.animate('tempo', 10, 20, duration=2, mode='beats')
            # klick1.animate('test', 'bite', 10, 20, duration=2)
            # self.wait(1, '') # forbidden

        if address == '/set_route':
            engine.set_route(args[0])

        if address == '/play':
            klick1.start()
            klick2.start()

        elif address == '/stop':
            klick1.stop()
            klick2.stop()


    def scene(self):

        klick1.start(), self.wait(1), klick1.stop(), self.wait(1),
        klick1.start(), self.wait(1), klick1.stop(), self.wait(1),
