"""Guardas comunes de las tools: scope, logging y traducción de errores."""

from __future__ import annotations

import functools
import inspect
import logging
from typing import Any, Awaitable, Callable, TypeVar

from ..auth import current_auth, require_scope
from ..errors import (
    BackendError,
    ToolFailure,
    as_tool_error,
    translate_exception,
)
from ..logs import Timer, log_tool_call

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def _arguments(fn: Callable[..., Any], args: tuple, kwargs: dict) -> dict[str, Any]:
    try:
        bound = inspect.signature(fn).bind_partial(*args, **kwargs)
        return {
            key: value.model_dump() if hasattr(value, "model_dump") else value
            for key, value in bound.arguments.items()
        }
    except (TypeError, ValueError):
        return {**kwargs}


def tool_guard(tool: str, scope: str) -> Callable[[F], F]:
    """Exige el scope, mide latencia, registra la invocación y normaliza errores."""

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            arguments = _arguments(fn, args, kwargs)
            timer = Timer()
            auth_info = current_auth()

            try:
                auth_info = require_scope(
                    scope, tool=tool, arguments=arguments
                )
            except ToolFailure as exc:
                log_tool_call(
                    tool=tool,
                    auth_info=auth_info,
                    arguments=arguments,
                    outcome="denied",
                    error_code=str(exc.code),
                    duration_ms=timer.stop(),
                )
                raise as_tool_error(
                    exc.code,
                    exc.message,
                    tool=tool,
                    details=exc.details,
                ) from exc

            try:
                result = await fn(*args, **kwargs)
            except ToolFailure as exc:
                log_tool_call(
                    tool=tool,
                    auth_info=auth_info,
                    arguments=arguments,
                    outcome="error",
                    error_code=str(exc.code),
                    duration_ms=timer.stop(),
                )
                raise as_tool_error(
                    exc.code,
                    exc.message,
                    tool=tool,
                    details=exc.details,
                ) from exc
            except BackendError as exc:
                failure = translate_exception(exc)
                log_tool_call(
                    tool=tool,
                    auth_info=auth_info,
                    arguments=arguments,
                    outcome="error",
                    error_code=str(failure.code),
                    duration_ms=timer.stop(),
                    backend_status=exc.status_code,
                )
                raise as_tool_error(
                    failure.code,
                    failure.message,
                    tool=tool,
                    details=failure.details,
                ) from exc
            except Exception as exc:  # noqa: BLE001 - fallback controlado
                failure = translate_exception(exc)
                logger.exception("Fallo no controlado en la tool %s", tool)
                log_tool_call(
                    tool=tool,
                    auth_info=auth_info,
                    arguments=arguments,
                    outcome="error",
                    error_code=str(failure.code),
                    duration_ms=timer.stop(),
                    extra={"exception_type": type(exc).__name__},
                )
                raise as_tool_error(
                    failure.code,
                    failure.message,
                    tool=tool,
                ) from exc

            log_tool_call(
                tool=tool,
                auth_info=auth_info,
                arguments=arguments,
                outcome="success",
                duration_ms=timer.stop(),
            )
            return result

        return wrapper  # type: ignore[return-value]

    return decorator


__all__ = ["tool_guard"]
