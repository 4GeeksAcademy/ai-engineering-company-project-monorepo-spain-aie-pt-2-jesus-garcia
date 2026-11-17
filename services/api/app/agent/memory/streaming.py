"""Extractor incremental de la respuesta visible de un JSON en streaming.

La generación con memoria pide al modelo un único objeto JSON con dos campos:
``respuesta`` (lo que ve el usuario) y ``propuesta_memoria`` (metadato interno).
Si enviásemos los deltas tal cual, el usuario vería llaves y comillas. Este
extractor sigue el valor de la cadena ``respuesta`` y emite solo su contenido,
aunque los deltas lleguen partidos en cualquier posición.
"""

from __future__ import annotations

import re

_VISIBLE_KEY_RE = re.compile(r'"(?:respuesta|answer)"\s*:\s*"')

#: Suficiente para reconocer una clave partida entre dos deltas.
_KEY_LOOKBEHIND = 48

_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}


class AnswerStreamExtractor:
    """Convierte deltas de un JSON OpenAI-compatible en texto visible."""

    def __init__(self) -> None:
        self._mode = "detect"  # detect | seek_key | in_string | done | passthrough
        self._buffer = ""
        self._escape = False
        self._unicode: str | None = None
        self._high_surrogate: int | None = None
        self._emitted = False

    @property
    def emitted(self) -> bool:
        return self._emitted

    @property
    def passthrough(self) -> bool:
        return self._mode == "passthrough"

    def feed(self, delta: str) -> str:
        if not delta:
            return ""
        if self._mode == "passthrough":
            return self._emit(delta)
        if self._mode == "done":
            return ""

        if self._mode == "detect":
            self._buffer_since_start = getattr(self, "_buffer_since_start", "") + delta
            stripped = self._buffer_since_start.lstrip()
            if not stripped:
                return ""
            if stripped[0] != "{":
                self._mode = "passthrough"
                text = self._buffer_since_start
                self._buffer_since_start = ""
                return self._emit(text)
            self._buffer = stripped
            self._buffer_since_start = ""
            self._mode = "seek_key"
            return self._consume_buffer()

        if self._mode == "seek_key":
            self._buffer += delta
            return self._consume_buffer()

        return self._consume_string(delta)

    def finish(self) -> str:
        """Cierra el stream. No inventa contenido que no se haya emitido."""

        self._buffer = ""
        return ""

    def _consume_buffer(self) -> str:
        match = _VISIBLE_KEY_RE.search(self._buffer)
        if match is None:
            if len(self._buffer) > _KEY_LOOKBEHIND:
                self._buffer = self._buffer[-_KEY_LOOKBEHIND:]
            return ""
        remainder = self._buffer[match.end():]
        self._buffer = ""
        self._mode = "in_string"
        return self._consume_string(remainder)

    def _consume_string(self, text: str) -> str:
        emitted: list[str] = []
        index = 0
        length = len(text)

        while index < length and self._mode == "in_string":
            char = text[index]

            if self._unicode is not None:
                self._unicode += char
                index += 1
                if len(self._unicode) < 4:
                    continue
                digits = self._unicode
                self._unicode = None
                try:
                    code = int(digits, 16)
                except ValueError:
                    continue
                emitted.append(self._decode_code_point(code))
                continue

            if self._escape:
                self._escape = False
                if char == "u":
                    self._unicode = ""
                else:
                    emitted.append(_ESCAPES.get(char, char))
                index += 1
                continue

            if char == "\\":
                self._escape = True
                index += 1
                continue

            if char == '"':
                self._mode = "done"
                index += 1
                break

            emitted.append(char)
            index += 1

        if self._mode == "in_string" and text:
            # Nada pendiente: el bucle consume todo el texto recibido.
            pass
        return self._emit("".join(emitted))

    def _decode_code_point(self, code: int) -> str:
        if 0xD800 <= code <= 0xDBFF:
            # Mitad alta de un par surrogate: se espera la mitad baja.
            self._high_surrogate = code
            return ""
        if 0xDC00 <= code <= 0xDFFF:
            high = self._high_surrogate
            self._high_surrogate = None
            if high is None:
                return "\ufffd"
            return chr(0x10000 + ((high - 0xD800) << 10) + (code - 0xDC00))
        self._high_surrogate = None
        return chr(code)

    def _emit(self, text: str) -> str:
        if not text:
            return ""
        self._emitted = True
        return text


__all__ = ["AnswerStreamExtractor"]
