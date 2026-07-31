from worker.ring_buffer import FrameRingBuffer


def test_empty_buffer():
    buf = FrameRingBuffer(max_seconds=10, fps=5)
    assert len(buf) == 0
    assert buf.oldest_ts is None
    assert buf.newest_ts is None
    assert buf.snapshot(0, 100) == []


def test_append_and_snapshot_window():
    buf = FrameRingBuffer(max_seconds=60, fps=1)
    for ts in range(10):
        buf.append(float(ts), f"frame-{ts}".encode())

    window = buf.snapshot(3.0, 6.0)
    assert [ts for ts, _ in window] == [3.0, 4.0, 5.0, 6.0]
    assert window[0][1] == b"frame-3"


def test_capacity_evicts_oldest():
    # 5 s à 2 fps = 10 frames de capacité.
    buf = FrameRingBuffer(max_seconds=5, fps=2)
    for ts in range(25):
        buf.append(float(ts), b"x")

    assert len(buf) == 10
    assert buf.oldest_ts == 15.0
    assert buf.newest_ts == 24.0
    # Les frames écrasées ne sont plus accessibles.
    assert buf.snapshot(0, 14) == []


def test_capacity_is_at_least_one():
    buf = FrameRingBuffer(max_seconds=0, fps=0.1)
    buf.append(1.0, b"a")
    buf.append(2.0, b"b")
    assert len(buf) == 1
    assert buf.newest_ts == 2.0
