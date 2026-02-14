# File: ai-news-radio/scripts/protocols.py
# AI-SUMMARY: Volcano Engine PodcastTTS WebSocket binary protocol implementation.
# Copied from official SDK (volcengine.speech.volc_speech_python_sdk_1.0.0.25)

import io
import logging
import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Callable, List

import websockets

logger = logging.getLogger(__name__)


class MsgType(IntEnum):
    Invalid = 0
    FullClientRequest = 0b1
    AudioOnlyClient = 0b10
    FullServerResponse = 0b1001
    AudioOnlyServer = 0b1011
    FrontEndResultServer = 0b1100
    Error = 0b1111
    ServerACK = AudioOnlyServer


class MsgTypeFlagBits(IntEnum):
    NoSeq = 0
    PositiveSeq = 0b1
    LastNoSeq = 0b10
    NegativeSeq = 0b11
    WithEvent = 0b100


class VersionBits(IntEnum):
    Version1 = 1


class HeaderSizeBits(IntEnum):
    HeaderSize4 = 1


class SerializationBits(IntEnum):
    Raw = 0
    JSON = 0b1
    Thrift = 0b11
    Custom = 0b1111


class CompressionBits(IntEnum):
    None_ = 0
    Gzip = 0b1
    Custom = 0b1111


class EventType(IntEnum):
    None_ = 0
    StartConnection = 1
    FinishConnection = 2
    ConnectionStarted = 50
    ConnectionFailed = 51
    ConnectionFinished = 52
    StartSession = 100
    CancelSession = 101
    FinishSession = 102
    SessionStarted = 150
    SessionCanceled = 151
    SessionFinished = 152
    SessionFailed = 153
    UsageResponse = 154
    PodcastRoundStart = 360
    PodcastRoundResponse = 361
    PodcastRoundEnd = 362
    PodcastEnd = 363


@dataclass
class Message:
    version: VersionBits = VersionBits.Version1
    header_size: HeaderSizeBits = HeaderSizeBits.HeaderSize4
    type: MsgType = MsgType.Invalid
    flag: MsgTypeFlagBits = MsgTypeFlagBits.NoSeq
    serialization: SerializationBits = SerializationBits.JSON
    compression: CompressionBits = CompressionBits.None_
    event: EventType = EventType.None_
    session_id: str = ""
    connect_id: str = ""
    sequence: int = 0
    error_code: int = 0
    payload: bytes = b""

    @classmethod
    def from_bytes(cls, data: bytes) -> "Message":
        if len(data) < 3:
            raise ValueError(f"Data too short: {len(data)} bytes")
        type_and_flag = data[1]
        msg = cls(
            type=MsgType(type_and_flag >> 4),
            flag=MsgTypeFlagBits(type_and_flag & 0b00001111),
        )
        msg.unmarshal(data)
        return msg

    def marshal(self) -> bytes:
        buf = io.BytesIO()
        header = [
            (self.version << 4) | self.header_size,
            (self.type << 4) | self.flag,
            (self.serialization << 4) | self.compression,
        ]
        header_size = 4 * self.header_size
        header.extend([0] * (header_size - len(header)))
        buf.write(bytes(header))
        for w in self._get_writers():
            w(buf)
        return buf.getvalue()

    def unmarshal(self, data: bytes) -> None:
        buf = io.BytesIO(data)
        vh = buf.read(1)[0]
        self.version = VersionBits(vh >> 4)
        self.header_size = HeaderSizeBits(vh & 0b00001111)
        buf.read(1)
        sc = buf.read(1)[0]
        self.serialization = SerializationBits(sc >> 4)
        self.compression = CompressionBits(sc & 0b00001111)
        padding = 4 * self.header_size - 3
        if padding > 0:
            buf.read(padding)
        for r in self._get_readers():
            r(buf)

    def _get_writers(self) -> List[Callable]:
        writers = []
        if self.flag == MsgTypeFlagBits.WithEvent:
            writers.extend([self._write_event, self._write_session_id])
        if self.type in (
            MsgType.FullClientRequest, MsgType.FullServerResponse,
            MsgType.FrontEndResultServer, MsgType.AudioOnlyClient,
            MsgType.AudioOnlyServer,
        ):
            if self.flag in (MsgTypeFlagBits.PositiveSeq, MsgTypeFlagBits.NegativeSeq):
                writers.append(self._write_sequence)
        elif self.type == MsgType.Error:
            writers.append(self._write_error_code)
        writers.append(self._write_payload)
        return writers

    def _get_readers(self) -> List[Callable]:
        readers = []
        if self.type in (
            MsgType.FullClientRequest, MsgType.FullServerResponse,
            MsgType.FrontEndResultServer, MsgType.AudioOnlyClient,
            MsgType.AudioOnlyServer,
        ):
            if self.flag in (MsgTypeFlagBits.PositiveSeq, MsgTypeFlagBits.NegativeSeq):
                readers.append(self._read_sequence)
        elif self.type == MsgType.Error:
            readers.append(self._read_error_code)
        if self.flag == MsgTypeFlagBits.WithEvent:
            readers.extend([self._read_event, self._read_session_id, self._read_connect_id])
        readers.append(self._read_payload)
        return readers

    def _write_event(self, buf):
        buf.write(struct.pack(">i", self.event))

    def _write_session_id(self, buf):
        if self.event in (EventType.StartConnection, EventType.FinishConnection,
                          EventType.ConnectionStarted, EventType.ConnectionFailed):
            return
        sid = self.session_id.encode("utf-8")
        buf.write(struct.pack(">I", len(sid)))
        buf.write(sid)

    def _write_sequence(self, buf):
        buf.write(struct.pack(">i", self.sequence))

    def _write_error_code(self, buf):
        buf.write(struct.pack(">I", self.error_code))

    def _write_payload(self, buf):
        buf.write(struct.pack(">I", len(self.payload)))
        buf.write(self.payload)

    def _read_event(self, buf):
        b = buf.read(4)
        if b:
            self.event = EventType(struct.unpack(">i", b)[0])

    def _read_session_id(self, buf):
        if self.event in (EventType.StartConnection, EventType.FinishConnection,
                          EventType.ConnectionStarted, EventType.ConnectionFailed,
                          EventType.ConnectionFinished):
            return
        b = buf.read(4)
        if b:
            size = struct.unpack(">I", b)[0]
            if size > 0:
                self.session_id = buf.read(size).decode("utf-8")

    def _read_connect_id(self, buf):
        if self.event in (EventType.ConnectionStarted, EventType.ConnectionFailed,
                          EventType.ConnectionFinished):
            b = buf.read(4)
            if b:
                size = struct.unpack(">I", b)[0]
                if size > 0:
                    self.connect_id = buf.read(size).decode("utf-8")

    def _read_sequence(self, buf):
        b = buf.read(4)
        if b:
            self.sequence = struct.unpack(">i", b)[0]

    def _read_error_code(self, buf):
        b = buf.read(4)
        if b:
            self.error_code = struct.unpack(">I", b)[0]

    def _read_payload(self, buf):
        b = buf.read(4)
        if b:
            size = struct.unpack(">I", b)[0]
            if size > 0:
                self.payload = buf.read(size)


async def receive_message(ws) -> Message:
    data = await ws.recv()
    if isinstance(data, str):
        raise ValueError(f"Unexpected text message: {data}")
    return Message.from_bytes(data)


async def wait_for_event(ws, msg_type: MsgType, event_type: EventType) -> Message:
    msg = await receive_message(ws)
    if msg.type != msg_type or msg.event != event_type:
        raise ValueError(f"Expected {msg_type}/{event_type}, got {msg.type}/{msg.event}")
    return msg


async def start_connection(ws) -> None:
    msg = Message(type=MsgType.FullClientRequest, flag=MsgTypeFlagBits.WithEvent)
    msg.event = EventType.StartConnection
    msg.payload = b"{}"
    await ws.send(msg.marshal())


async def finish_connection(ws) -> None:
    msg = Message(type=MsgType.FullClientRequest, flag=MsgTypeFlagBits.WithEvent)
    msg.event = EventType.FinishConnection
    msg.payload = b"{}"
    await ws.send(msg.marshal())


async def start_session(ws, payload: bytes, session_id: str) -> None:
    msg = Message(type=MsgType.FullClientRequest, flag=MsgTypeFlagBits.WithEvent)
    msg.event = EventType.StartSession
    msg.session_id = session_id
    msg.payload = payload
    await ws.send(msg.marshal())


async def finish_session(ws, session_id: str) -> None:
    msg = Message(type=MsgType.FullClientRequest, flag=MsgTypeFlagBits.WithEvent)
    msg.event = EventType.FinishSession
    msg.session_id = session_id
    msg.payload = b"{}"
    await ws.send(msg.marshal())
