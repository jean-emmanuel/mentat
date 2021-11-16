from modules import *

class Audio():

    def part(self, *args, **kwargs):

        print('trackA audio route:', args)
        klick1.set('tempo', 34)
        self.engine.start_cycle()
        self.start_scene('x', self.test)

    def test(self):

        print(1)
        self.wait(1, 'b')
        print(2)
        self.wait_next_cycle()
        print(1)
