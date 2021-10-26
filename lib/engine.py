import logging
LOGGER = logging.getLogger(__name__)

import time
import liblo
import queue
import fnmatch
import atexit
import sys
import os
import pyinotify
from pyalsa import alsaseq
from signal import signal, SIGINT, SIGTERM

from .config import *
from .midi import osc_to_midi, midi_to_osc
from .thread import KillableThread as Thread
from .timer import Timer

class Engine():

    def __init__(self, name, port, folder):
        """
        Engine(name, port, folder)

        Engine constructor.

        :param name:
            client name
        :param port:
            osc input port, can be an udp port number or a unix socket path
        :param folder:
            path to config folder where state files will be saved to and loaded from
        """
        self.name = name

        self.osc_server = liblo.Server(port)
        self.osc_server.add_method(None, None, self.route_osc)
        self.osc_inputs = {}
        self.osc_outputs = {}

        self.midi_server = alsaseq.Sequencer(clientname=self.name)
        self.midi_ports = {}

        self.routes = {}
        self.active_route = None

        self.scenes = {}
        self.scenes_timers = {}

        self.is_running = False

        self.current_time = time.time()
        # self.timer = Timer(self)
        self.bpm = 120

        self.folder = folder
        self.modules = {}
        self.queue = []

        self.notifier = None

    def start(self):
        """
        start()

        Start engine.
        """

        signal(SIGINT, lambda a,b: self.stop())
        signal(SIGTERM, lambda a,b: self.stop())

        for name in self.modules:
            self.modules[name].initialize(self)
        for name in self.routes:
            self.routes[name].initialize(self)

        self.is_running = True

        last_animation = 0

        LOGGER.info('started')

        while self.is_running:

            self.current_time = time.time()

            # process osc messages
            while self.osc_server and self.osc_server.recv(0):
                pass

            # process midi messages
            midi_events = self.midi_server.receive_events()
            for e in midi_events:
                self.route_midi(e)

            # update animations
            if self.current_time - last_animation >= ANIMATION_PERIOD:
                last_animation = self.current_time
                for name in self.modules:
                    self.modules[name].update_animations()

            # send pending messages
            self.flush()

            # take some rest
            time.sleep(MAINLOOP_PERDIO)

        LOGGER.info('stopped')


    def stop(self):
        """
        stop()

        Stop engine.
        """

        LOGGER.info('stopping...')
        self.is_running = False
        self.stop_scene('*')
        if self.osc_server:
            self.osc_server.free()
            self.osc_server = None
        if self.notifier:
            try:
                self.notifier.stop()
                self.notifier = None
            except:
                pass

    def restart(self):
        """
        restart()

        Stop the engine and restart once the process is terminated.
        Borrowed from mididings.
        """
        def restart_python():
            os.execl(sys.executable, sys.executable, *sys.argv)
        atexit.register(restart_python)
        LOGGER.info('restarting...')
        self.stop()

    def autorestart(self):
        """
        autorestart()

        Watch main script and imported modules and call restart when they change.
        Borrowed from mididings.
        """
        wm = pyinotify.WatchManager()
        self.notifier = pyinotify.ThreadedNotifier(wm)
        base_dir = os.path.dirname(os.path.abspath(sys.modules['__main__'].__file__))
        # add watches for imported modules
        for m in sys.modules.values():
            # builtin modules don't have a __file__ attribute
            if hasattr(m, '__file__'):
                f = os.path.abspath(m.__file__)
                # only watch file if it's in the same directory as the main script
                if f.startswith(base_dir):
                    wm.add_watch(f, pyinotify.IN_MODIFY, lambda e: self.restart())
        self.notifier.start()

    def add_module(self, module):
        """
        add_module(module)

        Add a module.

        :param module: Module object
        """
        self.modules[module.name] = module

        if module.port is not None:
            if module.protocol == 'osc':
                self.osc_inputs[module.port] = module.name
                self.osc_outputs[module.name] = module.port
            elif module.protocol == 'midi':
                self.midi_ports[module.name] = self.midi_server.create_simple_port(module.name, alsaseq.SEQ_PORT_TYPE_MIDI_GENERIC | alsaseq.SEQ_PORT_TYPE_APPLICATION, alsaseq.SEQ_PORT_CAP_WRITE | alsaseq.SEQ_PORT_CAP_SUBS_WRITE | alsaseq.SEQ_PORT_CAP_READ | alsaseq.SEQ_PORT_CAP_SUBS_READ)

    def flush(self):
        """
        flush()

        Send messages in queue.
        """
        for message in self.queue:

            self.send(message.protocol, message.port, message.address, *message.args)

        self.queue = []

        self.midi_server.sync_output_queue()

    def send(self, protocol, port, address, *args):
        """
        send(protocol, port, address, *args)

        Send OSC / MIDI message.

        :param protocol: 'osc' or 'midi'
        :param port:
            module name or udp port number or unix socket path if protocol is 'osc'
        :param address: osc address
        :param args: values
        """
        if protocol == 'osc':

            if port in self.osc_outputs:
                port = self.osc_outputs[port]

            self.osc_server.send(port, address, *args)

        elif protocol == 'midi':

            if port in self.midi_ports:

                midi_event = osc_to_midi(address, args)
                if midi_event:
                    midi_event.source = (self.midi_server.client_id, self.midi_ports[port])
                    self.midi_server.output_event(midi_event)
                    self.midi_server.drain_output()

    def add_route(self, route):
        """
        add_route(route)

        Add a route.

        :param route: Route object
        """
        self.routes[route.name] = route

    def set_route(self, name):
        """
        set_route(name)

        Set active route.

        :param name: route name
        """
        if name in self.routes:
            if self.active_route:
                self.active_route.deactivate()
            self.active_route = self.routes[name]
            self.active_route.activate()
            LOGGER.info('active route set to "%s"' % name)
        else:
            LOGGER.error('route "%s" not found' % name)

    def route(self, protocol, port, address, args):
        """
        route(protocol, port, address, args)

        Unified route for osc and midi messages.

        :param protocol: 'osc' or 'midi'
        :param port: name of module or port number if unknown
        :param address: osc address
        :param args: list of values
        """
        if port in self.modules:
            self.modules[port].route(address, args)

        if self.active_route:
            self.active_route.route(protocol, port, address, args)

    def route_osc(self, address, args, types, src):
        """
        Route incoming raw osc events.
        """
        port = src.port
        if src.port in self.osc_inputs:
            port = self.osc_inputs[src.port]
        self.route('osc', port, address, args)

    def route_midi(self, event):
        """
        Route incoming raw midi events.
        """
        port = self.midi_server.get_port_info(event.dest[1],event.dest[0])['name']
        osc_message = midi_to_osc(event)
        if osc_message:
            osc_message['port'] = port
            self.route('midi', port, osc_message['address'], osc_message['args'])

    def start_scene(self, name, scene, *args, **kwargs):
        """
        scene(scene)

        Start function in a thread.
        If a scene with the same name is already running, it will be stopped.

        :param name: scene name
        :param scene: function or method
        :param *args: arguments for the scene function
        :param *kwargs: keyword arguments for the scene function
        """
        self.stop_scene(name)
        self.scenes_timers[name] = Timer(self)
        self.scenes[name] = Thread(target=scene, name=name, args=args, kwargs=kwargs)
        self.scenes[name].start()
        LOGGER.info('starting scene %s' % name)

    def stop_scene(self, name):
        """
        scene(scene)

        Stop scene thread.

        :param name: scene name
        :param scene: function or method
        """
        if '*' in name:
            for n in fnmatch.filter(self.scenes.keys(), name):
                self.stop_scene(n)
        elif name in self.scenes:
            if self.scenes[name].is_alive():
                LOGGER.info('stopping scene %s' % name)
                self.scenes[name].kill()
            else:
                LOGGER.info('cleaning scene %s' % name)
            id = self.scenes[name].ident
            del self.scenes[name]
            del self.scenes_timers[name]

    def get_scene_timer(self):
        """
        get_scene_timer()

        Threaded scenes each have a Timer object they can use to wait().
        Route objects can call self.wait(), but it is forbidden in the main thread.
        """
        name = Thread.get_current().name
        if name in self.scenes_timers:
            return self.scenes_timers[name]
        else:
            LOGGER.error('cannot call wait() from main thread')
            return None
