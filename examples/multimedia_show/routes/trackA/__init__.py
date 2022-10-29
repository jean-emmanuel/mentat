from ..global_route import GlobalRoute
from .audio import Audio
from .video import Video
from .light import Light
from modules import *

class TrackA(Light, Video, Audio, GlobalRoute):

    def __init__(self):

        super().__init__(name='A')
    def activate(self):
        klick1.set('tempo',1)
        klick1.set('tempo',2)
        klick1.set('tempo',3)
        klick1.set('tempo',4)

        # klick1.stop_animate('position_x')
        klick1.animate('position_x', 0, 1, 1, loop=True)
        klick1.animate('position', [None, -1, -1], [None, -2, -2], 1, loop=True)

    def part(self, *args, **kwargs):
        """
        Custom method to handle the different parts in the track
        in a sementic way
        """
        Audio.part(self, *args, **kwargs)
        Video.part(self, *args, **kwargs)
        Light.part(self, *args, **kwargs)

    def route(self, protocol, port, address, args):
        """
        Call parent class method first
        so that the order of routing is
        GlobalRoute -> TrackA
        """
        super().route(protocol, port, address, args)

        print('trackA main route:', args)

        if address == '/test':
            self.engine.root_module.save('globalstate')

        if address == '/set' and len(args) > 2:
            self.engine.root_module.set(*args)

        if address == '/animate' and len(args) > 2:
            self.engine.root_module.animate(*args)

        if address == '/save' and len(args) == 2:
            if args[0] in self.engine.modules:
                self.engine.modules[args[0]].save(args[1])

        if address == '/load' and len(args) == 2:
            if args[0] in self.engine.modules:
                self.engine.modules[args[0]].load(args[1])

        if address =='/pedalboard/button':
            if args[0] == 1:
                self.part("verse", 1)
            if args[0] == 2:
                self.part("verse", 2)
            if args[0] == 3:
                self.part("chorus")
