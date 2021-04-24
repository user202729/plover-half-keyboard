
def subprocess_plot_run(queue_)->None:
    import sys
    assert "plover" in sys.modules
    # actually this is unnecessary (and also incur some loading time), but it's hard to avoid

    from matplotlib import pyplot as plt
    figure, axe=plt.subplots()
    figure.show()

    from plover_half_keyboard import _Event, _StopThread
    import queue

    pressed_time={}
    segments=[]
    segments_changed=True

    while True:
        try:
            while True:
                event=queue_.get_nowait()
                if isinstance(event, _StopThread):
                    return

                [is_down, key, event_time]=event
                if is_down:
                    if key not in pressed_time: # STRAY_DOWN
                        pressed_time[key]=event_time
                else:
                    if key in pressed_time: # STRAY_UP
                        segments.append((pressed_time[key], event_time))
                        segments_changed=True
                        del pressed_time[key]

        except queue.Empty:
            pass


        if segments and segments_changed:
            segments_changed=False
            last_up=segments[-1][1]
            segments=[
                    segment for segment in segments
                    if segment[1]>=last_up-2
                    ]

            axe.clear()
            axe.plot(
                    [
                        [index for index, (press, release) in enumerate(segments)],
                        [index for index, (press, release) in enumerate(segments)],
                        ],
                    [
                        [(last_up-press)*1000 for index, (press, release) in enumerate(segments)],
                        [(last_up-release)*1000 for index, (press, release) in enumerate(segments)],
                        ],
                    "o-", linewidth=3, markersize=6
                    )
            axe.set_xlim(0, 20)
            axe.set_ylim(-10, 2000)
        
            figure.canvas.draw_idle()

        # alternatively use 'figure.raise_window'
        # TODO can event loop be used? Busy polling is not a good idea.
        figure.canvas.start_event_loop(0.5)
