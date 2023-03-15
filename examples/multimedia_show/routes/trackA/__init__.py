from ..global_route import GlobalRoute
from .audio import Audio
from .video import Video
from .light import Light
from modules import *
import time
class TrackA(Light, Video, Audio, GlobalRoute):

    def __init__(self):

        super().__init__(name='A')
    def activate(self):
        # klick1.set('tempo',1)
        # klick1.set('tempo',2)
        # klick1.set('tempo',3)
        # klick1.set('tempo',4)
        # x=time.time()
        #
        # def misc():
        #     print('metro going')
        #     # self.wait_next_cycle()
        #     # self.wait_next_cycle()
        #
        #     self.wait(8.2, 'b')
        #     # self.wait_next_cycle()
        #     # self.engine.send('osc', 10000, '/bpm', 60)
        #     # self.engine.set_tempo(60)
        #     # self.engine.send('osc', 10000, '/bpm', 360)
        #     # self.engine.set_tempo(360)
        #     self.engine.send('osc', 10000, '/bpm', 55)
        #     self.engine.set_tempo(55)
        #     # self.engine.set_time_signature('5/4')
        #     # print(self.engine.current_time)
        #     # self.engine.start_cycle()
        #     # self.engine.send('osc', 10000, '/play')
        #
        #     # self.wait(9.6)
        #     # self.engine.set_tempo(140)
        #     # self.engine.send('osc', 10000, '/bpm', 140)
        #
        #     # self.engine.start_cycle()
        #     # self.engine.send('osc', 10000, '/play')
        #
        # def a():
        #     print('A going')
        #     while True:
        #         kbd.send('/note_on',1, 64, 127)
        #         # self.wait(0.25,'b')
        #         kbd.send('/note_off',1, 64)
        #         # print('A')
        #         # self.wait_next_cycle()
        #         self.wait(1,'b')
        # def b():
        #     print('B going')
        #     while True:
        #         kbd.send('/note_on',1, 74, 127)
        #         # self.wait(0.25,'b')
        #         kbd.send('/note_off',1, 74)
        #         # print('B')
        #         # self.wait_next_cycle()
        #         self.wait(1,'b')
        # # self.engine.current_time = time.monotonic_ns()
        # self.engine.set_tempo(220)
        # self.engine.send('osc', 10000, '/bpm', 220)
        # self.engine.send('osc', 10000, '/play')
        # self.engine.start_cycle()
        #
        # self.start_scene('misc', misc)
        # self.start_scene('scA', a)
        # time.sleep(0.33)
        # self.start_scene('scB', b)
        #
        #
        #
        #
        #
        self.start_scene('tune',self.tune)

    def tune(self):
        while True:
            self.wait(1, 's')
            # fluid : midi tuning (MTS)
            tuning=[0.5,0,0,0,0,0,0,0,0,0,0,0]
            mtc = [
                0xF0, # sysex
                0x7F, # realtime
                0x7F, # device id (any)
                0x08, # tuning request
                0x09, # octave tune

                0x7F, # channels
                0x7F, # channels
                0x7F, # channels
            ]
            for t in tuning:
                cents = int((t + 1) / 2 * 16383)
                mtc += [
                    (cents  >> 7) & 0x7F, # note tuning lsb
                    cents & 0x7F, # note tuning msb
                ]

            mtc.append(0xF7)
            kbd.send('/sysex', *mtc)





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

        if address == '/test':
            def scene():
                with self.lock():
                    self.stop_scene('test')
                    for i in range(140):
                        klick1.set('tempo',i)
                    with self.lock():

                        klick1.reset('tempo')
                    klick1.set('tempo',2)
            self.start_scene('test', scene)
