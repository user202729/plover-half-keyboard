"For use with a NKRO computer keyboard as a steno machine."

import time
import queue
import collections
import threading
from typing import Set, NamedTuple, Deque, Union, Optional, Dict

#from plover import _
from plover.machine.base import StenotypeBase
from plover.misc import boolean
from plover.oslayer.keyboardcontrol import KeyboardCapture


# i18n: Machine name.
#_._('Half Keyboard')


class _Event(NamedTuple):
    is_down: bool
    key: str
    event_time: float #time.time()


class _StopThread(Exception): pass


MAX_DOWN_GAP=0.05
MIN_OVERLAP=0.1
MAX_OVERLAP=0.2
MAX_UP_GAP=0.05
DELAY_TIME=0.02 # sufficiently small, but not too small to save CPU time


class HalfKeyboard(StenotypeBase):
    """Standard stenotype interface for a computer keyboard.

    This class implements the three methods necessary for a standard
    stenotype interface: start_capture, stop_capture, and
    add_callback.

    """

    KEYS_LAYOUT = KeyboardCapture.SUPPORTED_KEYS_LAYOUT
    ACTIONS = ("Mark as chord", "Mark as keys", "Change to chord", "Change to keys")

    def __init__(self, params):
        """Monitor the keyboard's events."""
        super().__init__()
        self._is_suppressed = False

        self._keyboard_capture = None
        self._last_stroke_key_down_count = 0
        self._update_bindings()

        self._events_queue: queue.Queue[Union[_Event, _StopThread]] = queue.Queue()

        self._event_processing_thread = threading.Thread(target=self._event_processing_thread_run)

    def _event_processing_thread_run(self)->None:
        # counting those **received** from self._events_queue
        # i.e., **actual** (hardware) pressed
        # NOT those emulated
        pressed: Set[str]=set()

        #what is current: see reset_chord below
        current_might_be_chord: bool=True

        pending_events: Deque[_Event]=collections.deque()


        def process_one_pending()->None:
            [is_down, key, event_time]=pending_events.popleft()
            if is_down:
                KEY_TO_SINGLE_STROKE={
                        "a": ["A-", "*"],
                        "b": ["P-", "W-", "*"],
                        "c": ["K-", "R-", "*"],
                        "d": ["T-", "K-", "*"],
                        "e": ["*", "-E"],
                        "f": ["T-", "P-", "*"],
                        "g": ["T-", "K-", "P-", "W-", "*"],
                        "h": ["H-", "*"],
                        "i": ["*", "-E", "-U"],
                        "j": ["S-", "K-", "W-", "R-", "*"],
                        "k": ["K-", "*"],
                        "l": ["H-", "R-", "*"],
                        "m": ["P-", "H-", "*"],
                        "n": ["T-", "P-", "H-", "*"],
                        "o": ["O-", "*"],
                        "p": ["P-", "*"],
                        "q": ["K-", "W-", "*"],
                        "r": ["R-", "*"],
                        "s": ["S-", "*"],
                        "t": ["T-", "*"],
                        "u": ["*", "-U"],
                        "v": ["S-", "R-", "*"],
                        "w": ["W-", "*"],
                        "x": ["K-", "P-", "*"],
                        "y": ["K-", "W-", "R-", "*"],
                        "z": ["S-", "T-", "K-", "P-", "W-", "*"],

                        "BackSpace": ["P-", "W-", "-F", "-P"],
                        #"Delete": [],
                        #"Down": [],
                        #"End": [],
                        #"Escape": [],
                        #"Home": [],
                        #"Insert": [],
                        #"Left": [],
                        #"Page_Down": [],
                        #"Page_Up": [],
                        #"Return": [],
                        #"Right": [],
                        #"Tab": [],
                        #"Up": [],
                        "space": ["S-", "-P"],

                        }
                if key in KEY_TO_SINGLE_STROKE:
                    self._notify(KEY_TO_SINGLE_STROKE[key])
                else:
                    print(f"TODO support {key=}")
            else:
                pass

        def process_pending()->None:
            while pending_events:
                process_one_pending()


        def can_be_chord_part(current: float=None)->bool:
            """
            Check if pending_events can be prefix of a chord.

            pending_events must not be mutated during the execution of this function.
            (it's probably not possible anyway without another thread modifying it)

            pressed must be consistent.
            """
            if current is None: current=time.time()

            assert current_might_be_chord #otherwise what's the point of checking?

            if not pending_events: return True

            assert pending_events[0].is_down

            first_is_up=next(
                    (
                        index for index, event in enumerate(pending_events)
                        if not event.is_down
                        )
                    , len(pending_events))
            assert first_is_up>=1

            down_gap=pending_events[first_is_up-1].event_time-pending_events[0].event_time
            if down_gap>MAX_DOWN_GAP:
                print(f"Fail: {down_gap=}")
                return False

            time_to_last_event=current-pending_events[-1].event_time
            if time_to_last_event>max(MAX_OVERLAP, MAX_UP_GAP)+DELAY_TIME*2:
                print(f"Fail: {time_to_last_event=}")
                return False # NOTE not very strict, but is good enough

            if first_is_up==len(pending_events):
                return True

            if any(event.is_down for event in [*pending_events][first_is_up:]):
                print(f"Fail: alternative up/down")
                return False
            up_gap=pending_events[-1].event_time-pending_events[first_is_up].event_time
            if up_gap>MAX_UP_GAP:
                print(f"Fail: {up_gap=}")
                return False

            overlapping_gap=pending_events[first_is_up].event_time-pending_events[first_is_up-1].event_time
            if not (MIN_OVERLAP<=overlapping_gap<=MAX_OVERLAP):
                print(f"Fail: {overlapping_gap=}")
                return False

            print(f"All accepted: {down_gap=} {up_gap=} {overlapping_gap=}")
            return True

        def events_to_steno_keys(current: float=None)->Optional[Set[str]]:
            """
            Convert (pending_events) to a chord.
            Returns None if it should not be interpreted as a chord.
            """
            nonlocal current_might_be_chord
            assert current_might_be_chord
            assert can_be_chord_part(current)
            #if len(pending_events)==2: # ignore single key press
            #    return None
            return {
                    steno_key
                    for steno_key in
                    (self._bindings.get(key) for [is_down, key, event_time] in pending_events)
                    if steno_key is not None
                    }


        def process_actual_event(event: Union[_Event, _StopThread])->None:
            # called in near realtime, only once per event
            nonlocal current_might_be_chord

            if isinstance(event, _StopThread):
                process_pending()
                raise event
            pending_events.append(event)


            [is_down, key, event_time]=event

            if is_down:
                if key in pressed:
                    #user hold a key
                    current_might_be_chord=False
                    process_pending()
                else:
                    pressed.add(key)

            else:
                if key in pressed:
                    pressed.remove(key)
                    if not pressed:
                        # [reset_chord]
                        current=time.time()
                        if current_might_be_chord and can_be_chord_part(current):
                            steno_keys=events_to_steno_keys(current)
                            if not steno_keys: # the user might have stroked a stroke full of no-op?
                                process_pending()
                            else:
                                print(f"Send chord: {steno_keys=}")
                                self._notify(steno_keys)
                                pending_events.clear()
                        else:
                            process_pending()

                        current_might_be_chord=True

                else:
                    print(f"{key=} should have been in {pressed=}, or some modifier is held while the key is pressed down, (pressed, key)")
                    current_might_be_chord=False
                    process_pending()

        try:
            while True:
                # read actual events and process in "realtime"
                if pressed:
                    # wait for a little bit, even if there's no new events
                    # happens when the user holds a key for a while
                    time.sleep(DELAY_TIME)
                    try:
                        while True:
                            process_actual_event(self._events_queue.get_nowait())

                    except queue.Empty:
                        pass

                else:
                    # wait until next event
                    # happens when the user doesn't press any key
                    process_actual_event(self._events_queue.get())

                #there may be delayed (pending) events

                if current_might_be_chord and not can_be_chord_part():
                    assert pending_events
                    # because the empty sequence is the subsequence of any sequences (of events)

                    current_might_be_chord=False
                    process_pending()

        except _StopThread:
            pass
     


    def _suppress(self)->None:
        if self._keyboard_capture is None:
            return
        suppressed_keys = self._bindings.keys() if self._is_suppressed else ()
        self._keyboard_capture.suppress_keyboard(suppressed_keys)

    def _update_bindings(self)->None:
        # key ("x") -> mapping ("no-op" is None, otherwise steno key name)
        self._bindings: Dict[str, Optional[str]] = dict(self.keymap.get_bindings())
        for key, mapping in list(self._bindings.items()):
            if 'no-op' == mapping:
                self._bindings[key] = None
        self._suppress()

    def set_keymap(self, keymap)->None:
        super().set_keymap(keymap)
        self._update_bindings()

    def start_capture(self)->None:
        """Begin listening for output from the stenotype machine."""
        self._initializing()
        try:
            self._keyboard_capture = KeyboardCapture()
            self._keyboard_capture.key_down = self._key_down
            self._keyboard_capture.key_up = self._key_up
            self._suppress()
            self._keyboard_capture.start()
            self._event_processing_thread.start()
        except:
            self._error()
            raise
        self._ready()

    def stop_capture(self)->None:
        """Stop listening for output from the stenotype machine."""
        if self._keyboard_capture is not None:
            self._is_suppressed = False
            self._suppress()
            self._keyboard_capture.cancel()
            self._keyboard_capture = None
        self._events_queue.put(_StopThread())
        self._event_processing_thread.join()
        self._stopped()

    def set_suppression(self, enabled)->None:
        self._is_suppressed = enabled
        self._suppress()

    def suppress_last_stroke(self, send_backspaces)->None:
        send_backspaces(self._last_stroke_key_down_count)
        self._last_stroke_key_down_count = 0

    def _key_down(self, key)->None:
        """Called when a key is pressed."""
        assert key is not None

        if key in self._bindings and self._bindings[key] in self.ACTIONS:
            print(f"Special command pressed {self._bindings[key]}")
            return

        self._events_queue.put(_Event(True, key, time.time()))

    def _key_up(self, key)->None:
        """Called when a key is released."""
        assert key is not None

        if key in self._bindings and self._bindings[key] in self.ACTIONS:
            # special command
            return

        self._events_queue.put(_Event(False, key, time.time()))


    @classmethod
    def get_option_info(cls):
        return {}
