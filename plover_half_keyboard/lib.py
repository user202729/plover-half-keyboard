import time
import queue
import collections
import threading
import multiprocessing
from typing import Set, NamedTuple, Deque, Union, Optional, Dict, Sequence


class _Event(NamedTuple):
    is_down: bool
    key: str
    event_time: float #time.time()


class _StopThread(Exception): pass


DELAY_TIME=0.02
# the delay time between events being processed
# sufficiently small, but not too small to save CPU time


MAX_DOWN_GAP=0.05
MIN_OVERLAP=0.1
MAX_OVERLAP=0.2
MAX_UP_GAP=0.05


def can_be_chord_part(events: Sequence[_Event], current: float=None)->bool:
	"""
	Check if events can be prefix of a chord.

	events must not be mutated during the execution of this function.
	(it's probably not possible anyway without another thread modifying it)

	pressed must be consistent.
	"""
	if current is None: current=time.time()

	if not events: return True

	assert events[0].is_down

	first_is_up=next(
			(
				index for index, event in enumerate(events)
				if not event.is_down
				)
			, len(events))
	assert first_is_up>=1

	down_gap=events[first_is_up-1].event_time-events[0].event_time
	if down_gap>MAX_DOWN_GAP:
		print(f"Fail: {down_gap=}")
		return False

	time_to_last_event=current-events[-1].event_time
	if time_to_last_event>max(MAX_OVERLAP, MAX_UP_GAP)+DELAY_TIME*2:
		print(f"Fail: {time_to_last_event=}")
		return False # NOTE not very strict, but is good enough

	if first_is_up==len(events):
		return True

	if any(event.is_down for event in [*events][first_is_up:]):
		print(f"Fail: alternative up/down")
		return False
	up_gap=events[-1].event_time-events[first_is_up].event_time
	if up_gap>MAX_UP_GAP:
		print(f"Fail: {up_gap=}")
		return False

	overlapping_gap=events[first_is_up].event_time-events[first_is_up-1].event_time
	if not (MIN_OVERLAP<=overlapping_gap<=MAX_OVERLAP):
		print(f"Fail: {overlapping_gap=}")
		return False

	print(f"All accepted: {down_gap=} {up_gap=} {overlapping_gap=}")
	return True


def events_to_steno_keys(events: Sequence[_Event],
		bindings: Dict[str, Optional[str]],
		current: float=None)->Optional[Set[str]]:
	"""
	Convert (events) to a chord.
	Returns None if it should not be interpreted as a chord.
	"""
	assert can_be_chord_part(events, current)
	#if len(events)==2: # ignore single key press
	#    return None
	return {
			steno_key
			for steno_key in
			(bindings.get(key) for [is_down, key, event_time] in events)
			if steno_key is not None
			}
