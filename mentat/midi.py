"""
MIDI <-> OSC converter
"""

from pyalsa import alsaseq
from pyalsa.alsaseq import (SEQ_EVENT_NOTEON, SEQ_EVENT_NOTEOFF, SEQ_EVENT_CONTROLLER,
                            SEQ_EVENT_PGMCHANGE, SEQ_EVENT_PITCHBEND,SEQ_EVENT_SYSEX,
                            SEQ_EVENT_START, SEQ_EVENT_CONTINUE, SEQ_EVENT_STOP)

MIDI_TO_OSC = {
    SEQ_EVENT_NOTEON: '/note_on',
    SEQ_EVENT_NOTEOFF: '/note_off',
    SEQ_EVENT_CONTROLLER: '/control_change',
    SEQ_EVENT_PGMCHANGE: '/program_change',
    SEQ_EVENT_PITCHBEND: '/pitch_bend',
    SEQ_EVENT_SYSEX: '/sysex',
    SEQ_EVENT_START: '/start',
    SEQ_EVENT_CONTINUE: '/continue',
    SEQ_EVENT_STOP: '/stop'
    
}

OSC_TO_MIDI = {
    '/note_on': SEQ_EVENT_NOTEON,
    '/note_off': SEQ_EVENT_NOTEOFF,
    '/control_change': SEQ_EVENT_CONTROLLER,
    '/program_change': SEQ_EVENT_PGMCHANGE,
    '/pitch_bend': SEQ_EVENT_PITCHBEND,
    '/sysex': SEQ_EVENT_SYSEX,
    '/start': SEQ_EVENT_START,
    '/continue': SEQ_EVENT_CONTINUE,
    '/stop': SEQ_EVENT_STOP
}

def midi_to_osc(event):
    """
    Convert SeqEvent to OSC
    """

    mtype = event.type

    if mtype not in MIDI_TO_OSC:
        return None

    data = event.get_data()

    osc = {}
    osc['address'] = MIDI_TO_OSC[mtype]

    if mtype is SEQ_EVENT_NOTEON:
        osc['args'] = [data['note.channel'], data['note.note'], data['note.velocity']]
    elif mtype is SEQ_EVENT_NOTEOFF:
        osc['args'] = [data['note.channel'], data['note.note'], 0]
    elif mtype in (SEQ_EVENT_PITCHBEND, SEQ_EVENT_PGMCHANGE):
        osc['args'] = [data['control.channel'], data['control.value']]
    elif mtype is SEQ_EVENT_SYSEX:
        osc['args'] = data['ext']
    elif mtype is SEQ_EVENT_CONTROLLER:
        osc['args'] = [data['control.channel'], data['control.param'], data['control.value']]
    elif mtype in (SEQ_EVENT_START, SEQ_EVENT_CONTINUE, SEQ_EVENT_STOP):
        osc['args'] = []
    else:
        return None

    return osc

def osc_to_midi(address, args):
    """
    Convert OSC message to SeqEvent
    """

    if address not in OSC_TO_MIDI:
        return None

    iargs = []
    for arg in args:
        if isinstance(arg, tuple):
            arg = arg[1]
        if arg is None:
            return None
        if not isinstance(arg, int):
            arg = int(arg)
        iargs.append(arg)

    mtype = OSC_TO_MIDI[address]
    event = alsaseq.SeqEvent(mtype)

    if mtype == SEQ_EVENT_NOTEON:

        event.set_data({'note.channel': iargs[0],
                        'note.note': iargs[1],
                        'note.velocity': iargs[2]})

    elif mtype == SEQ_EVENT_NOTEOFF:

        event.set_data({'note.channel': iargs[0],
                        'note.note': iargs[1]})

    elif mtype in (SEQ_EVENT_PITCHBEND, SEQ_EVENT_PGMCHANGE):

        event.set_data({'control.channel': iargs[0],
                        'control.value': iargs[1]})

    elif mtype == SEQ_EVENT_SYSEX:

        event.set_data({'ext': iargs})

    elif mtype == SEQ_EVENT_CONTROLLER:

        event.set_data({'control.channel': iargs[0],
                        'control.param': iargs[1],
                        'control.value': iargs[2]})

    return event
