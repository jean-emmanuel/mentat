from ..global_route import GlobalRoute
from .audio import Audio
from .video import Video
from .light import Light

class TrackA(Light, Video, Audio, GlobalRoute):

    def __init__(self):

        super().__init__(name='A')


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

        if address == '/set' and len(args) > 2:
            if args[0] in self.engine.modules:
                self.engine.modules[args[0]].set(*args[1:])

        if address == '/set_condition' and len(args) > 2:
            if args[0] in self.engine.modules:
                self.engine.modules[args[0]].set_condition(*args[1:])


        if address =='/pedalboard/button':
            if args[0] == 1:
                self.part("verse", 1)
            if args[0] == 2:
                self.part("verse", 2)
            if args[0] == 3:
                self.part("chorus")
