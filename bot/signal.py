from typing import Optional, Callable, Union
import datetime, websocket, json, copy, queue, threading, time
from . import exceptions

class Signal:
    """
    Custom Web Socket app connector that fetches messages / signals from
    the running Status Backend Docker container. Currently this class works
    only with `/signals`
    """

    def __init__(self, url: str):
        self.__url = url
        self.__data = {}
        self.__signal_type = None
        self.__error_message = None
        # For real time data extraction
        self.__queue = queue.Queue()
        self.__thread = None
        # State for the long-lived `connect()` + `expect()` flow. These
        # attributes are intentionally single-underscore so `SignalExpectation`
        # can read them without name-mangling gymnastics.
        self._cond = threading.Condition()
        self._received_by_type: dict[str, list[dict]] = {}
        self._received_all: list[tuple[int, str, dict]] = []
        self._seq = 0
        self.__connect_thread: Optional[threading.Thread] = None
        self.__connect_ws: Optional[websocket.WebSocketApp] = None
        self.__should_stop = False

    def __on_open(self, ws: websocket.WebSocketApp):
        """
        Used to reset class variables before messages / signals
        listening starts
        """
        self.__data = {}
        self.__error_message = None

    def close(self, ws: websocket.WebSocketApp, *args):
        """
        Used to reset class variables after messages / signals
        have stopped listening or when the object is deleted
        """
        self.__signal_type = None
        self.__close_thread()

    def __on_error(self, ws: websocket.WebSocketApp, error: str):
        """
        Triggered when Status Backend (Docker container) breaks
        """
        self.__error_message = f"There was an error with the Status Backend Docker container... Please look at the Docker logs for more information.\nError message: {error}"

    def __get_message(self, ws: websocket.WebSocketApp, signal: str):
        """
        Process Status Backend signal and exit. This is used in `get`.
        """
        signal: dict = json.loads(signal)
        if signal["type"] != self.__signal_type:
            return

        event: Optional[dict] = signal.get("event", {})
        # Sometimes event can be returned as `None`
        if not event:
            event = {}

        self.__data = {
            "timestamp": datetime.datetime.fromtimestamp(signal["timestamp"]),
            "is_error": not isinstance(event.get("error"), type(None)),
            "error_message": event.get("error"),
            "event": event
        }
        ws.close()

    def get(self, signal_type: str) -> dict:
        """
        Run the the connector to monitor Status Backend for a single message.
        NOTE: If not careful, the websocket can end up in an infinite loop

        Parameters:
            - `signal_type` - the "type" as it is in Status Backend

        Output:
            - the signal data point
        """
        self.__signal_type = signal_type
        ws = websocket.WebSocketApp(
            self.__url,
            on_open=self.__on_open,
            on_message=self.__get_message,
            on_close=self.close,
            on_error=self.__on_error
        )
        ws.run_forever()

        if self.__error_message:
            raise exceptions.SignalError(self.__error_message)

        return copy.deepcopy(self.__data)

    def __listen_message(self, ws: websocket.WebSocketApp, signal: str):
        """
        Listen continuously for Status Backend signals
        """
        signal: dict = json.loads(signal)
        if signal["type"] != self.__signal_type:
            return

        event: Optional[dict] = signal.get("event", {}) or {}
        data = {
            "timestamp": datetime.datetime.fromtimestamp(signal["timestamp"]),
            "is_error": not isinstance(event.get("error"), type(None)),
            "error_message": event.get("error"),
            "event": event
        }
        self.__queue.put(data)

    def __close_thread(self):
        """
        Called in `listen` / object is deleted and safely close it
        """
        if not self.__thread:
            return

        if self.__thread.is_alive():
            self.__thread.join(1)

    def listen(self, signal_type: str):
        """
        Listen for a specific Signal forever

        Parameters:
            - `signal_type` - the "type" as it is in Status Backend
        """
        self.__signal_type = signal_type
        ws = websocket.WebSocketApp(
            self.__url,
            on_open=self.__on_open,
            on_message=self.__listen_message,
            on_close=self.close,
            on_error=self.__on_error
        )
        self.__thread = threading.Thread(target=ws.run_forever, daemon=True)
        self.__thread.start()
        while True:
            try:
                data = self.__queue.get()
            except KeyboardInterrupt:
                break
            if self.__error_message:
                raise exceptions.SignalError(self.__error_message)

            yield data

    def connect(self):
        """
        Open a persistent websocket connection that buffers every incoming signal
        for inspection via `expect()`. Must be called before `expect()`. Idempotent
        - calling twice while a connection is alive is a no-op.

        The connection auto-reconnects on disconnect with exponential backoff,
        so `expect()` keeps working across transient backend hiccups.
        """
        if self.__connect_thread and self.__connect_thread.is_alive():
            return
        self.__should_stop = False
        self.__connect_thread = threading.Thread(target=self.__connect_loop, daemon=True)
        self.__connect_thread.start()

    def disconnect(self):
        """
        Tear down the persistent connection opened by `connect()`. Idempotent.
        Safe to call even if `connect()` was never invoked.
        """
        self.__should_stop = True
        if self.__connect_ws is not None:
            self.__connect_ws.close()
        if self.__connect_thread and self.__connect_thread.is_alive():
            self.__connect_thread.join(timeout=1)

    def __connect_loop(self):
        """
        Background loop that maintains the persistent websocket and reconnects
        with exponential backoff on disconnect, until `disconnect()` is called.
        """
        retry_delay = 0.5
        max_delay = 5.0
        while not self.__should_stop:
            self.__connect_ws = websocket.WebSocketApp(
                self.__url,
                on_message=self.__buffer_message,
                on_error=self.__on_error,
            )
            self.__connect_ws.run_forever()
            if self.__should_stop:
                break
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_delay)

    def __buffer_message(self, ws: websocket.WebSocketApp, raw: str):
        """
        Persistent-connection on_message handler. Parses the raw signal, normalizes
        the payload, and appends it to both the per-type buffer and the global
        ordered stream. Notifies any threads waiting in `SignalExpectation.__exit__`.
        """
        try:
            signal: dict = json.loads(raw)
        except json.JSONDecodeError:
            return

        signal_type = signal.get("type")
        if not signal_type:
            return

        event: dict = signal.get("event") or {}
        data = {
            "type": signal_type,
            "timestamp": datetime.datetime.fromtimestamp(signal["timestamp"]),
            "is_error": event.get("error") is not None,
            "error_message": event.get("error"),
            "event": event,
        }
        with self._cond:
            self._seq += 1
            self._received_by_type.setdefault(signal_type, []).append(data)
            self._received_all.append((self._seq, signal_type, data))
            self._cond.notify_all()

    def expect(
        self,
        signal_type: str,
        *,
        count: int = 1,
        accept_fn: Optional[Callable[[dict], bool]] = None,
        pattern: Optional[str] = None,
        predicate: Optional[Callable[[dict], bool]] = None,
        timeout: float = 20.0,
        start: Union[str, int] = "now",
    ) -> "SignalExpectation":
        """
        Return a context manager that waits for `count` matching signals of `signal_type`
        to arrive after entering the `with` block. Perform the triggering action inside the
        block. After the block exits the matched signals are exposed as `exp.result` (or
        `exp.results` when `count > 1`).

        Requires `connect()` to be running. Raises `TimeoutError` if the expected signals
        do not arrive within `timeout` seconds.

        Parameters:
            - `signal_type` - the "type" as it appears in Status Backend
            - `count` - number of matching signals to wait for (default 1)
            - `accept_fn` - optional filter; called with the buffered signal dict
            - `pattern` - optional substring to match in the JSON-serialized signal
            - `predicate` - alias for `accept_fn`. Only one of these three may be set.
            - `timeout` - max seconds to wait inside `__exit__`
            - `start` - `"now"` (default, only future signals), `"beginning"` (search
              from the start of the buffer) or an explicit int index
        """
        if not self.__connect_thread or not self.__connect_thread.is_alive():
            raise exceptions.SignalError("connect() must be called before expect()")

        return SignalExpectation(
            self,
            signal_type,
            count=count,
            accept_fn=accept_fn,
            pattern=pattern,
            predicate=predicate,
            timeout=timeout,
            start=start,
        )


class SignalExpectation:
    """
    Context manager that asserts an action triggers one or more matching signals.

    On `__enter__` it snapshots the current size of the per-type signal buffer so
    any signals received before the action are ignored (race-safe). On `__exit__`
    it blocks until `count` matching signals appear past the snapshot or until
    `timeout` expires, in which case `TimeoutError` is raised.

    Typical usage:

        signal.connect()
        with signal.expect("messages.new") as exp:
            account.send_message(chat_id, "hello")
        print(exp.result)
    """

    def __init__(
        self,
        signal: Signal,
        signal_type: str,
        *,
        count: int = 1,
        accept_fn: Optional[Callable[[dict], bool]] = None,
        pattern: Optional[str] = None,
        predicate: Optional[Callable[[dict], bool]] = None,
        timeout: float = 20.0,
        start: Union[str, int] = "now",
    ):
        if count < 1:
            raise ValueError("count must be >= 1")

        filters_set = sum(1 for v in (accept_fn, pattern, predicate) if v is not None)
        if filters_set > 1:
            raise ValueError("Only one of accept_fn, pattern, predicate can be specified")

        self._signal = signal
        self._signal_type = signal_type
        self._count = count
        self._timeout = float(timeout)
        self._start = start
        self._start_index = 0

        if pattern is not None:
            self._accept_fn: Optional[Callable[[dict], bool]] = lambda s: pattern in json.dumps(s, default=str)
        elif predicate is not None:
            self._accept_fn = predicate
        else:
            self._accept_fn = accept_fn

        self.result: Optional[Union[dict, list[dict]]] = None
        self.results: Optional[list[dict]] = None

    def __enter__(self) -> "SignalExpectation":
        with self._signal._cond:
            buffer = self._signal._received_by_type.setdefault(self._signal_type, [])
            if self._start == "now":
                self._start_index = len(buffer)
            elif self._start == "beginning":
                self._start_index = 0
            elif isinstance(self._start, int):
                if self._start < 0:
                    raise ValueError("start index must be >= 0")
                self._start_index = self._start
            else:
                raise ValueError(f"Unsupported start mode: {self._start!r}")
        return self

    def __exit__(self, exc_type, exc, tb):
        # Don't swallow exceptions raised inside the `with` body.
        if exc_type is not None:
            return False

        deadline = time.time() + self._timeout
        with self._signal._cond:
            while True:
                buffer = self._signal._received_by_type.get(self._signal_type, [])
                candidates = buffer[self._start_index:]
                if self._accept_fn is not None:
                    candidates = [s for s in candidates if self._accept_fn(s)]

                if len(candidates) >= self._count:
                    self.results = candidates[: self._count]
                    self.result = self.results[0] if self._count == 1 else self.results
                    return False

                remaining = deadline - time.time()
                if remaining <= 0:
                    raise TimeoutError(
                        f"Expected {self._count} signal(s) of type {self._signal_type!r}, "
                        f"got {len(candidates)} within {self._timeout}s"
                    )

                self._signal._cond.wait(timeout=remaining)

