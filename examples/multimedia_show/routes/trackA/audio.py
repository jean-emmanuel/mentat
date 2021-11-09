class Audio():

    def part(self, *args, **kwargs):

        super().part(*args, **kwargs)

        print('trackA audio route:', args)

        self.start_scene('x', self.test)

    def test(self):
        print('scene launched')
