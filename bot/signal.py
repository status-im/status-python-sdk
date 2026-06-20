from typing import Optional
import datetime, websocket, json, copy, queue, threading
from . import exceptions

class Signal:
    """
    Custom Web Socket app connector that fetches messages / signals from
    the running Status Backend Docker container. Currently this class works
    only with `/signals`
    """

    # As of now signals should be kept internal until initial Python SDK
    # scope is defined. Then the SignalType from the tests can be reused.
    available_signals = [
        'messages.new', 'message.delivered', 'node.ready',
        'node.started', 'node.login', 'node.stopped'
    ]

    def __init__(self, url: str):
        self.__url = url
        self.__data = {}
        self.__signal_type = None
        self.__error_message = None
        # For real time data extraction
        self.__queue = queue.Queue()
        self.__thread = None

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

