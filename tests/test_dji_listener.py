#!/usr/bin/env python3
# Copyright Sensors & Signals LLC https://www.snstac.com/
# SPDX-License-Identifier: Apache-2.0
"""Lifecycle regression tests for the AntSDR scanner-push listener."""

import asyncio

import pytest

import pytak
from dronecot.classes import DJIListenerWorker


async def _wait_for_listener(worker):
    for _ in range(100):
        if worker._server is not None:  # pylint: disable=protected-access
            return worker._server  # pylint: disable=protected-access
        await asyncio.sleep(0.01)
    raise AssertionError("DJI listener did not start")


@pytest.mark.asyncio
async def test_listener_close_releases_active_client():
    """An active AntSDR connection must not keep DroneCOT alive on shutdown."""
    queue = asyncio.Queue()
    worker = DJIListenerWorker(
        queue,
        {"DJI_BIND_ADDRESS": "127.0.0.1", "DJI_TCP_PORT": 0},
    )
    run_task = asyncio.create_task(worker.run())
    writer = None

    try:
        server = await _wait_for_listener(worker)
        port = server.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"dji_O,test-frame\n")
        await writer.drain()
        assert await asyncio.wait_for(queue.get(), timeout=1.0) == b"dji_O,test-frame"

        await asyncio.wait_for(worker.close(), timeout=2.0)
        result = await asyncio.wait_for(
            asyncio.gather(run_task, return_exceptions=True), timeout=2.0
        )

        assert isinstance(result[0], asyncio.CancelledError)
        assert await asyncio.wait_for(reader.read(), timeout=1.0) == b""
        assert not worker._client_tasks  # pylint: disable=protected-access
        assert not worker._client_writers  # pylint: disable=protected-access

        # Cleanup is intentionally idempotent because PyTAK and run() can call
        # it concurrently during first-exception shutdown.
        await worker.close()
    finally:
        if writer is not None:
            writer.close()
        if not run_task.done():
            run_task.cancel()
            await asyncio.gather(run_task, return_exceptions=True)
        await worker.close()


@pytest.mark.asyncio
async def test_transport_failure_exits_with_active_listener_client():
    """A TAK failure must escape CLITool while an AntSDR remains connected."""
    fail = asyncio.Event()

    class _FailingTransportWorker:
        async def run(self):
            await fail.wait()
            raise ConnectionAbortedError("WebSocket closed by server")

        async def close(self):
            return

    config = {
        "COT_URL": "wss://takserver.example.com:8443/takproto/1",
        "PYTAK_NO_HELLO": True,
    }
    listener = DJIListenerWorker(
        asyncio.Queue(),
        {"DJI_BIND_ADDRESS": "127.0.0.1", "DJI_TCP_PORT": 0},
    )
    clitool = pytak.CLITool(config)
    clitool.add_task(listener)
    clitool.add_task(_FailingTransportWorker())
    run_task = asyncio.create_task(clitool.run())
    writer = None

    try:
        server = await _wait_for_listener(listener)
        port = server.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)

        fail.set()
        with pytest.raises(ConnectionAbortedError, match="closed by server"):
            await asyncio.wait_for(run_task, timeout=2.0)

        assert await asyncio.wait_for(reader.read(), timeout=1.0) == b""
        assert not listener._client_tasks  # pylint: disable=protected-access
        assert not listener._client_writers  # pylint: disable=protected-access
    finally:
        if writer is not None:
            writer.close()
        if not run_task.done():
            run_task.cancel()
            await asyncio.gather(run_task, return_exceptions=True)
        await listener.close()
