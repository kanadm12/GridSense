"""Opt-in pytest plugin for SQLite, SQLAlchemy, and FastAPI lifecycle traces.

Load explicitly with ``-p pytest_lifecycle_instrumentation`` and set
``GRIDSENSE_LIFECYCLE_LOG`` to a disposable JSONL path. This module is never
imported by the application runtime.
"""

from __future__ import annotations

import gc
import inspect
import json
import os
import threading
import time
import weakref
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

_LOG_PATH = os.environ.get("GRIDSENSE_LIFECYCLE_LOG")
if not _LOG_PATH:
    raise RuntimeError(
        "Set GRIDSENSE_LIFECYCLE_LOG to a disposable JSONL file before "
        "loading pytest_lifecycle_instrumentation."
    )

_lock = threading.Lock()
_state_lock = threading.Lock()
_counter_lock = threading.Lock()
_identity_lock = threading.RLock()
_counters: dict[str, int] = defaultdict(int)
_identities: dict[tuple[str, int], tuple[weakref.ReferenceType[Any] | None, str]] = {}
_checked_out: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
_operations: dict[tuple[str, str], int] = defaultdict(int)
_active_sessions: dict[str, set[str]] = defaultdict(set)
_session_engines: dict[str, set[str]] = defaultdict(set)
_gc_callback = None
_log_stream = None
_event_count = 0


def _next_id(kind: str) -> str:
    with _counter_lock:
        _counters[kind] += 1
        return f"{kind}-{_counters[kind]}"


def _identity(kind: str, value: Any) -> str:
    key = (kind, id(value))
    with _identity_lock:
        entry = _identities.get(key)
        if entry is not None:
            reference, label = entry
            if reference is None or reference() is value:
                return label

        label = _next_id(kind)

        def forget(_reference: Any, identity_key: tuple[str, int] = key) -> None:
            with _identity_lock:
                _identities.pop(identity_key, None)

        try:
            reference = weakref.ref(value, forget)
        except TypeError:
            reference = None
        _identities[key] = (reference, label)
        return label


def _forget_identity(kind: str, value: Any) -> None:
    key = (kind, id(value))
    with _identity_lock:
        entry = _identities.get(key)
        if entry is not None and (entry[0] is None or entry[0]() is value):
            _identities.pop(key, None)


def _thread() -> dict[str, Any]:
    current = threading.current_thread()
    return {
        "thread_id": _identity("thread", current),
        "thread_ident": threading.get_ident(),
        "thread_name": current.name,
    }


def _emit(event: str, **fields: Any) -> None:
    global _event_count, _log_stream
    record = {
        "monotonic_ns": time.monotonic_ns(),
        "event": event,
        **_thread(),
        **fields,
    }
    encoded = json.dumps(record, separators=(",", ":"), default=str)
    with _lock:
        if _log_stream is None:
            _log_stream = Path(_LOG_PATH).open("a", encoding="utf-8", buffering=65536)
        _log_stream.write(encoded + "\n")
        _event_count += 1
        if (
            _event_count % 128 == 0
            or event.startswith(
                (
                    "engine.",
                    "metadata.",
                    "session.close",
                    "testclient.",
                    "dependency_overrides.",
                    "background_task.",
                    "test.",
                )
            )
            or event in {"pool.close", "pool.invalidate", "connection.error"}
            or (
                event == "connection.operation.start"
                and fields.get("concurrent_operations_same_dbapi", 0) > 0
            )
        ):
            _log_stream.flush()


def _safe_key(key: Any) -> str:
    module = getattr(key, "__module__", "")
    name = getattr(key, "__qualname__", type(key).__qualname__)
    return f"{module}.{name}" if module else name


def _pool_counts(engine: Any) -> dict[str, Any]:
    pool = engine.pool
    result: dict[str, Any] = {"pool_type": type(pool).__qualname__}
    for name in ("checkedout", "size", "overflow"):
        getter = getattr(pool, name, None)
        if callable(getter):
            try:
                result[name] = getter()
            except Exception as error:
                result[f"{name}_error"] = type(error).__qualname__
    return result


def _install_sqlalchemy_instrumentation() -> None:
    import sqlalchemy
    from sqlalchemy import event
    from sqlalchemy.engine import Connection, Engine
    from sqlalchemy.orm import Session
    from sqlalchemy.schema import MetaData

    original_create_engine = sqlalchemy.create_engine

    def create_engine(*args: Any, **kwargs: Any) -> Any:
        engine = original_create_engine(*args, **kwargs)
        engine_id = _identity("engine", engine)
        frame = next(
            (
                item
                for item in inspect.stack()[1:]
                if "sqlalchemy" not in item.filename.replace("\\", "/").lower()
                and item.filename != __file__
            ),
            None,
        )
        creator = (
            {
                "file": Path(frame.filename).name,
                "line": frame.lineno,
                "function": frame.function,
            }
            if frame
            else None
        )
        _emit(
            "engine.create",
            engine_id=engine_id,
            dialect=engine.dialect.name,
            pool_type=type(engine.pool).__qualname__,
            creator=creator,
        )

        def dbapi_id(connection: Any) -> str:
            return _identity("dbapi", connection)

        def on_connect(dbapi_connection: Any, connection_record: Any) -> None:
            connection_record.info["gridsense_lifecycle_dbapi_id"] = dbapi_id(
                dbapi_connection
            )
            _emit(
                "pool.connect",
                engine_id=engine_id,
                dbapi_id=dbapi_id(dbapi_connection),
                connection_record_id=_identity("connection-record", connection_record),
            )

        def on_checkout(
            dbapi_connection: Any,
            connection_record: Any,
            _connection_proxy: Any,
        ) -> None:
            connection_id = dbapi_id(dbapi_connection)
            checkout = {
                "checkout_id": _next_id("checkout"),
                "thread_id": _identity("thread", threading.current_thread()),
                "thread_ident": threading.get_ident(),
                "thread_name": threading.current_thread().name,
            }
            key = (engine_id, connection_id)
            with _state_lock:
                existing = _checked_out[key]
                previous = existing.copy()
                existing.append(checkout)
            _emit(
                "pool.checkout",
                engine_id=engine_id,
                dbapi_id=connection_id,
                connection_record_id=_identity("connection-record", connection_record),
                checkout_id=checkout["checkout_id"],
                checked_out_same_dbapi=len(previous),
                prior_checkouts=previous,
            )

        def on_checkin(dbapi_connection: Any, connection_record: Any) -> None:
            connection_id = dbapi_id(dbapi_connection) if dbapi_connection else None
            key = (engine_id, connection_id) if connection_id else None
            with _state_lock:
                active = _checked_out.get(key, []) if key else []
                checkout = active.pop(0) if active else None
                remaining = len(active)
                if key and not active:
                    _checked_out.pop(key, None)
            _emit(
                "pool.checkin",
                engine_id=engine_id,
                dbapi_id=connection_id,
                connection_record_id=_identity("connection-record", connection_record),
                checkout_id=checkout["checkout_id"] if checkout else None,
                checkout_thread_id=checkout["thread_id"] if checkout else None,
                checkout_thread_name=checkout["thread_name"] if checkout else None,
                remaining_same_dbapi_checkouts=remaining,
            )

        def on_close(dbapi_connection: Any, connection_record: Any) -> None:
            _emit(
                "pool.close",
                engine_id=engine_id,
                dbapi_id=dbapi_id(dbapi_connection),
                connection_record_id=_identity("connection-record", connection_record),
            )
            _forget_identity("dbapi", dbapi_connection)

        def on_invalidate(
            dbapi_connection: Any, connection_record: Any, exception: Any
        ) -> None:
            _emit(
                "pool.invalidate",
                engine_id=engine_id,
                dbapi_id=dbapi_id(dbapi_connection) if dbapi_connection else None,
                connection_record_id=_identity("connection-record", connection_record),
                exception_type=type(exception).__qualname__ if exception else None,
            )

        event.listen(engine.pool, "connect", on_connect)
        event.listen(engine.pool, "checkout", on_checkout)
        event.listen(engine.pool, "checkin", on_checkin)
        event.listen(engine.pool, "close", on_close)
        event.listen(engine.pool, "invalidate", on_invalidate)

        def before_cursor_execute(
            connection: Any,
            cursor: Any,
            statement: str,
            _parameters: Any,
            _context: Any,
            _executemany: bool,
        ) -> None:
            raw_connection = connection.connection.driver_connection
            connection_id = dbapi_id(raw_connection)
            key = (engine_id, connection_id)
            with _state_lock:
                in_flight = _operations[key]
                _operations[key] = in_flight + 1
                checkouts = [checkout.copy() for checkout in _checked_out[key]]
            _emit(
                "connection.operation.start",
                engine_id=engine_id,
                sqlalchemy_connection_id=_identity("connection", connection),
                dbapi_id=connection_id,
                operation=statement.lstrip().split(None, 1)[0].upper()
                if statement.strip()
                else "EMPTY",
                concurrent_operations_same_dbapi=in_flight,
                active_checkout_ids=[checkout["checkout_id"] for checkout in checkouts],
                active_checkout_threads=[
                    {
                        "thread_id": checkout["thread_id"],
                        "thread_ident": checkout["thread_ident"],
                        "thread_name": checkout["thread_name"],
                    }
                    for checkout in checkouts
                ],
                operation_thread_matches_checkout=any(
                    checkout["thread_ident"] == threading.get_ident()
                    for checkout in checkouts
                ),
            )

        def finish_cursor_execute(
            connection: Any,
            _cursor: Any,
            _statement: str,
            _parameters: Any,
            _context: Any,
            _executemany: bool,
        ) -> None:
            finish_operation(connection, "connection.operation.end")

        def finish_operation(connection: Any, event_name: str) -> None:
            raw_connection = connection.connection.driver_connection
            connection_id = dbapi_id(raw_connection)
            key = (engine_id, connection_id)
            with _state_lock:
                active = _operations.get(key, 0)
                _operations[key] = max(0, active - 1)
                remaining = _operations[key]
            _emit(
                event_name,
                engine_id=engine_id,
                sqlalchemy_connection_id=_identity("connection", connection),
                dbapi_id=connection_id,
                remaining_operations_same_dbapi=remaining,
            )

        def handle_error(exception_context: Any) -> None:
            connection = exception_context.connection
            if connection is not None:
                finish_operation(connection, "connection.operation.error")
            _emit(
                "connection.error",
                engine_id=engine_id,
                exception_type=type(exception_context.original_exception).__qualname__
                if exception_context.original_exception
                else None,
            )

        event.listen(engine, "before_cursor_execute", before_cursor_execute)
        event.listen(engine, "after_cursor_execute", finish_cursor_execute)
        event.listen(engine, "handle_error", handle_error)

        for event_name in ("begin", "commit", "rollback"):
            def connection_event(connection: Any, name: str = event_name) -> None:
                _emit(
                    f"connection.{name}",
                    engine_id=engine_id,
                    sqlalchemy_connection_id=_identity("connection", connection),
                    dbapi_id=dbapi_id(connection.connection.driver_connection)
                    if not connection.closed
                    else None,
                )

            event.listen(engine, event_name, connection_event)

        engine.dispose = _wrap_engine_dispose(engine, engine_id)
        return engine

    sqlalchemy.create_engine = create_engine

    original_session_init = Session.__init__

    def init_session(session: Session, *args: Any, **kwargs: Any) -> None:
        original_session_init(session, *args, **kwargs)
        _emit("session.create", session_id=_identity("session", session))

    Session.__init__ = init_session
    for event_name in ("after_commit", "after_rollback", "after_soft_rollback"):
        def session_event(session: Session, *_args: Any, name: str = event_name) -> None:
            _emit(
                f"session.{name.removeprefix('after_')}",
                session_id=_identity("session", session),
            )

        event.listen(Session, event_name, session_event)

    for event_name in ("after_transaction_create", "after_transaction_end"):
        def transaction_event(
            session: Session, transaction: Any, name: str = event_name
        ) -> None:
            _emit(
                f"session.transaction.{name.removeprefix('after_transaction_')}",
                session_id=_identity("session", session),
                transaction_id=_identity("transaction", transaction),
                nested=transaction.nested,
            )

        event.listen(Session, event_name, transaction_event)

    def session_after_begin(
        session: Session, _transaction: Any, connection: Any
    ) -> None:
        session_id = _identity("session", session)
        engine_id = _identity("engine", connection.engine)
        with _state_lock:
            _active_sessions[engine_id].add(session_id)
            _session_engines[session_id].add(engine_id)
        _emit(
            "session.connection",
            session_id=session_id,
            engine_id=engine_id,
            sqlalchemy_connection_id=_identity("connection", connection),
            dbapi_id=_identity("dbapi", connection.connection.driver_connection),
        )

    event.listen(Session, "after_begin", session_after_begin)

    original_close = Session.close

    def close_session(session: Session) -> None:
        session_id = _identity("session", session)
        _emit("session.close.start", session_id=session_id)
        try:
            original_close(session)
        finally:
            with _state_lock:
                engine_ids = _session_engines.pop(session_id, set())
                for engine_id in engine_ids:
                    _active_sessions[engine_id].discard(session_id)
                    if not _active_sessions[engine_id]:
                        _active_sessions.pop(engine_id, None)
            _emit("session.close.end", session_id=session_id)

    Session.close = close_session

    original_connection_close = Connection.close

    def close_connection(connection: Connection) -> None:
        engine_id = _identity("engine", connection.engine)
        connection_id = _identity("connection", connection)
        try:
            dbapi_id = _identity("dbapi", connection.connection.driver_connection)
        except Exception:
            dbapi_id = None
        _emit(
            "connection.close.start",
            engine_id=engine_id,
            sqlalchemy_connection_id=connection_id,
            dbapi_id=dbapi_id,
        )
        try:
            original_connection_close(connection)
        finally:
            _emit(
                "connection.close.end",
                engine_id=engine_id,
                sqlalchemy_connection_id=connection_id,
                dbapi_id=dbapi_id,
            )

    Connection.close = close_connection

    for method_name in ("create_all", "drop_all"):
        original_method = getattr(MetaData, method_name)

        def schema_method(
            metadata: MetaData,
            bind: Any = None,
            *args: Any,
            _name: str = method_name,
            _original: Any = original_method,
            **kwargs: Any,
        ) -> Any:
            engine = getattr(bind, "engine", bind)
            engine_id = _identity("engine", engine) if isinstance(engine, Engine) else None
            counts = _pool_counts(engine) if isinstance(engine, Engine) else {}
            active_sessions = (
                len(_active_sessions.get(engine_id, set())) if engine_id else None
            )
            _emit(
                f"metadata.{_name}.start",
                engine_id=engine_id,
                table_count=len(metadata.tables),
                pool=counts,
                active_sessions=active_sessions,
            )
            _assert_clean_lifecycle(
                f"metadata.{_name}", engine_id, counts, active_sessions
            )
            try:
                return _original(metadata, bind, *args, **kwargs)
            finally:
                _emit(
                    f"metadata.{_name}.end",
                    engine_id=engine_id,
                    table_count=len(metadata.tables),
                    pool=_pool_counts(engine) if isinstance(engine, Engine) else {},
                )

        setattr(MetaData, method_name, schema_method)


def _wrap_engine_dispose(engine: Any, engine_id: str) -> Any:
    original_dispose = engine.dispose

    def dispose(*args: Any, **kwargs: Any) -> Any:
        counts = _pool_counts(engine)
        with _state_lock:
            active_sessions = len(_active_sessions.get(engine_id, set()))
        _emit(
            "engine.dispose.start",
            engine_id=engine_id,
            pool=counts,
            active_sessions=active_sessions,
        )
        _assert_clean_lifecycle("engine.dispose", engine_id, counts, active_sessions)
        try:
            return original_dispose(*args, **kwargs)
        finally:
            _emit("engine.dispose.end", engine_id=engine_id, pool=_pool_counts(engine))

    return dispose


def _assert_clean_lifecycle(
    operation: str,
    engine_id: str | None,
    pool: dict[str, Any],
    active_sessions: int | None,
) -> None:
    if os.environ.get("GRIDSENSE_LIFECYCLE_ASSERT_CLEAN") != "1":
        return
    checkedout = pool.get("checkedout")
    if (checkedout is not None and checkedout > 0) or (
        active_sessions is not None and active_sessions > 0
    ):
        _emit(
            "lifecycle.leak.detected",
            operation=operation,
            engine_id=engine_id,
            checked_out_connections=checkedout,
            active_sessions=active_sessions,
        )
        raise AssertionError(
            f"{operation} for {engine_id} started with checked-out connections "
            "or active sessions"
        )


def _install_fastapi_instrumentation() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    class OverrideMap(dict):
        def __setitem__(self, key: Any, value: Any) -> None:
            _emit("dependency_overrides.set", dependency=_safe_key(key))
            super().__setitem__(key, value)

        def __delitem__(self, key: Any) -> None:
            _emit("dependency_overrides.delete", dependency=_safe_key(key))
            super().__delitem__(key)

        def clear(self) -> None:
            _emit("dependency_overrides.clear", count=len(self))
            super().clear()

        def update(self, *args: Any, **kwargs: Any) -> None:
            incoming = dict(*args, **kwargs)
            _emit(
                "dependency_overrides.update",
                count=len(incoming),
                dependencies=[_safe_key(key) for key in incoming],
            )
            super().update(incoming)

        def pop(self, key: Any, *args: Any) -> Any:
            _emit("dependency_overrides.pop", dependency=_safe_key(key))
            return super().pop(key, *args)

    original_init = FastAPI.__init__

    def init(app: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(app, *args, **kwargs)
        app.dependency_overrides = OverrideMap(app.dependency_overrides)
        _emit("fastapi.app.create", app_id=_identity("fastapi-app", app))

    FastAPI.__init__ = init

    original_enter = TestClient.__enter__
    original_exit = TestClient.__exit__

    def enter(client: TestClient) -> TestClient:
        client_id = _identity("testclient", client)
        _emit("testclient.enter.start", client_id=client_id)
        try:
            result = original_enter(client)
        except BaseException as error:
            _emit(
                "testclient.enter.error",
                client_id=client_id,
                exception_type=type(error).__qualname__,
            )
            raise
        _emit("testclient.enter.end", client_id=client_id)
        return result

    def exit_client(client: TestClient, *args: Any, **kwargs: Any) -> Any:
        client_id = _identity("testclient", client)
        _emit("testclient.exit.start", client_id=client_id)
        try:
            return original_exit(client, *args, **kwargs)
        finally:
            _emit("testclient.exit.end", client_id=client_id)

    TestClient.__enter__ = enter
    TestClient.__exit__ = exit_client


def _install_background_task_instrumentation() -> None:
    from starlette.background import BackgroundTask

    original_call = BackgroundTask.__call__

    async def call(task: BackgroundTask) -> Any:
        task_id = _identity("background-task", task)
        _emit("background_task.start", task_id=task_id)
        try:
            return await original_call(task)
        except BaseException as error:
            _emit(
                "background_task.error",
                task_id=task_id,
                exception_type=type(error).__qualname__,
            )
            raise
        finally:
            _emit("background_task.complete", task_id=task_id)

    BackgroundTask.__call__ = call


def pytest_configure(config: Any) -> None:
    global _gc_callback, _log_stream
    Path(_LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
    _log_stream = Path(_LOG_PATH).open("a", encoding="utf-8", buffering=65536)
    _install_sqlalchemy_instrumentation()
    _install_fastapi_instrumentation()
    _install_background_task_instrumentation()

    def on_gc(phase: str, info: dict[str, Any]) -> None:
        if phase == "stop":
            _emit(
                "gc.collection",
                generation=info.get("generation"),
                collected=info.get("collected"),
                uncollectable=info.get("uncollectable"),
            )

    _gc_callback = on_gc
    gc.callbacks.append(on_gc)
    config.addinivalue_line("markers", "native_lifecycle: lifecycle trace run")
    _emit("instrumentation.enabled", plugin="pytest_lifecycle_instrumentation")


def pytest_unconfigure(config: Any) -> None:
    global _log_stream
    del config
    if _gc_callback is not None:
        try:
            gc.callbacks.remove(_gc_callback)
        except ValueError:
            pass
    with _lock:
        if _log_stream is not None:
            _log_stream.flush()
            _log_stream.close()
            _log_stream = None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item: Any) -> Any:
    _emit("test.setup.start", nodeid=item.nodeid)
    outcome = yield
    _emit(
        "test.setup.end",
        nodeid=item.nodeid,
        failed=outcome.excinfo is not None,
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: Any) -> Any:
    _emit("test.call.start", nodeid=item.nodeid)
    outcome = yield
    _emit("test.call.end", nodeid=item.nodeid, failed=outcome.excinfo is not None)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item: Any, nextitem: Any) -> Any:
    _emit(
        "test.teardown.start",
        nodeid=item.nodeid,
        next_nodeid=nextitem.nodeid if nextitem else None,
    )
    outcome = yield
    _emit(
        "test.teardown.end",
        nodeid=item.nodeid,
        failed=outcome.excinfo is not None,
    )


def pytest_runtest_logreport(report: Any) -> None:
    if report.when in {"setup", "call", "teardown"}:
        _emit(
            f"test.{report.when}.complete",
            nodeid=report.nodeid,
            outcome=report.outcome,
        )
