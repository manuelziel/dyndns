#!/usr/bin/env python3
"""Daemon management module for background service execution.

Provides ``DaemonManager`` for running periodic application cycles with
reentrancy-safe POSIX signal handling (``SIGTERM``, ``SIGINT``, ``SIGHUP``),
monotonic interval scheduling, and graceful shutdown.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import signal
import threading
import time
from typing import Any

from .core.constants import DaemonDefaults

################################################################################
# DAEMON MANAGER CLASS
################################################################################


class DaemonManager:
    """Lifecycle and signal manager for long-running background operation.

    Attributes:
        application: Application instance exposing ``run_cycle()``.
        config: Configuration manager with daemon timing settings.
        logger: Logger instance for daemon lifecycle events.
        running: Whether the daemon loop is currently active.
    """

    def __init__(self, application: Any, config: Any, logger: Any) -> None:
        """Initialize daemon manager and register POSIX signal handlers.

        Args:
            application: Application instance exposing ``run_cycle()``.
            config: Configuration object with daemon settings.
            logger: Logger instance for daemon logging.
        """
        self.application = application
        self.config = config
        self.logger = logger

        self.running = False
        self._stop_event = threading.Event()
        self._shutdown_signal: int | None = None
        self._reload_requested = False
        self._cleaned_up = False
        self._daemon_thread: threading.Thread | None = None

        self._setup_signal_handlers()
        self.logger.debug("Daemon manager initialized")

    ############################################################################
    # PUBLIC INTERFACE - Daemon Lifecycle Management
    ############################################################################

    def start(self) -> bool:
        """Start the daemon loop in a dedicated background thread.

        Returns:
            True if started, False if already running or thread spawn failed.
        """
        if self.running:
            self.logger.warning("Daemon is already running")
            return False
        self.logger.info("Starting daemon...")
        try:
            self.running = True
            self._cleaned_up = False
            self._shutdown_signal = None
            self._stop_event.clear()
            self._daemon_thread = threading.Thread(
                target=self._daemon_loop, name="DaemonLoop", daemon=False
            )
            self._daemon_thread.start()
            self.logger.info("Daemon started successfully")
            return True
        except RuntimeError as exc:
            self.logger.error(f"Failed to start daemon: {exc}")
            self.running = False
            return False

    def stop(self) -> bool:
        """Stop the daemon gracefully within ``DaemonDefaults.STOP_TIMEOUT``.

        Returns:
            True if stopped cleanly, False if not running or join timed out.
        """
        if not self.running and self._cleaned_up:
            return True
        if not self.running and not self._stop_event.is_set():
            self.logger.warning("Daemon is not running")
            return False
        self.logger.info("Stopping daemon...")
        self._stop_event.set()
        self.running = False
        self._stop_application_component()
        if not self._join_daemon_thread():
            return False
        self._finalize_shutdown()
        self.logger.info("Daemon stopped successfully")
        return True

    def run_forever(self) -> None:
        """Run the daemon loop synchronously in the foreground thread.

        Raises:
            Exception: Re-raises fatal unhandled exceptions from the loop.
        """
        self.logger.debug("Starting daemon in foreground mode...")
        try:
            self.running = True
            self._cleaned_up = False
            self._shutdown_signal = None
            self._stop_event.clear()
            self._daemon_loop()
        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt, stopping...")
        except Exception as exc:
            self.logger.error(f"Daemon error: {exc}")
            raise
        finally:
            self.running = False
            self._stop_event.set()
            self._stop_application_component()
            self._finalize_shutdown()

    ############################################################################
    # PUBLIC INTERFACE - Status and Diagnostics
    ############################################################################

    def is_running(self) -> bool:
        """Return True when the daemon loop is active and not stopping.

        Returns:
            Boolean running status.
        """
        return self.running and not self._stop_event.is_set()

    def get_status(self) -> dict[str, Any]:
        """Collect current daemon runtime and thread status metrics.

        Returns:
            Dictionary describing daemon, stop event, and application state.
        """
        return {
            "running": self.running,
            "stop_requested": self._stop_event.is_set(),
            "thread_alive": self._daemon_thread.is_alive() if self._daemon_thread else False,
            "cycle_interval": self.config.daemon_check_interval,
            "application_running": (
                self.application.is_running()
                if hasattr(self.application, "is_running")
                else None
            ),
        }

    ############################################################################
    # PRIVATE METHODS - Signal Handling & Loop Execution
    ############################################################################

    def _setup_signal_handlers(self) -> None:
        """Register reentrancy-safe POSIX signal handlers on the main thread."""
        if threading.current_thread() is not threading.main_thread():
            self.logger.debug("Skipping signal registration outside main thread")
            return

        def handle_shutdown(signum: int, frame: Any) -> None:
            """Record shutdown signal and wake the stop event atomically."""
            _ = frame
            self._shutdown_signal = signum
            self._stop_event.set()

        def handle_reload(signum: int, frame: Any) -> None:
            """Flag deferred configuration reload on ``SIGHUP``."""
            _ = (signum, frame)
            self._reload_requested = True

        signal.signal(signal.SIGTERM, handle_shutdown)
        signal.signal(signal.SIGINT, handle_shutdown)
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, handle_reload)

    def _process_pending_signals(self) -> None:
        """Process deferred ``SIGHUP`` reload requests safely outside signal context."""
        if not self._reload_requested:
            return
        self._reload_requested = False
        self.logger.info("Received SIGHUP, reloading configuration...")
        try:
            if hasattr(self.application, "reload_config"):
                self.application.reload_config()
            else:
                self.logger.warning("Application does not support config reload")
        except Exception as exc:
            self.logger.error(f"Failed to reload configuration: {exc}")

    def _daemon_loop(self) -> None:
        """Execute application cycles at monotonic intervals until stopped."""
        self.logger.debug(
            f"Daemon loop started (interval: {self.config.daemon_check_interval}s)"
        )
        while self.running and not self._stop_event.is_set():
            self._process_pending_signals()
            self._run_single_timed_cycle()
        if self._shutdown_signal is not None:
            self.logger.info(
                f"Received signal {self._shutdown_signal}, initiating graceful shutdown..."
            )
        self.logger.debug("Daemon loop finished")

    def _run_single_timed_cycle(self) -> None:
        """Run one application cycle and wait for the remaining monotonic interval."""
        try:
            cycle_start = time.monotonic()
            if hasattr(self.application, "run_cycle"):
                if not self.application.run_cycle() and not self._stop_event.is_set():
                    self.logger.warning("Application cycle returned failure")
            else:
                self.logger.warning("Application does not have run_cycle method")
            duration = time.monotonic() - cycle_start
            sleep_time = max(0.0, self.config.daemon_check_interval - duration)
            if sleep_time > 0:
                self.logger.debug(
                    f"Cycle completed in {duration:.2f}s, sleeping for {sleep_time:.2f}s"
                )
                self._stop_event.wait(timeout=sleep_time)
            elif not self._stop_event.is_set():
                self.logger.warning(
                    f"Cycle took {duration:.2f}s, longer than interval "
                    f"{self.config.daemon_check_interval}s"
                )
        except Exception as exc:
            self.logger.error(f"Error in daemon loop: {exc}")
            self._stop_event.wait(timeout=self.config.daemon_retry_delay)

    def _stop_application_component(self) -> None:
        """Signal the wrapped ``Application`` instance to stop if supported."""
        if hasattr(self.application, "stop"):
            try:
                self.application.stop()
            except Exception as exc:
                self.logger.warning(f"Application stop failed: {exc}")

    def _join_daemon_thread(self) -> bool:
        """Join the background daemon thread when stopping from another thread.

        Returns:
            True if the thread exited within timeout, False otherwise.
        """
        if (
            self._daemon_thread is not None
            and self._daemon_thread.is_alive()
            and self._daemon_thread is not threading.current_thread()
        ):
            self.logger.debug("Waiting for daemon thread to finish...")
            self._daemon_thread.join(timeout=DaemonDefaults.STOP_TIMEOUT)
            if self._daemon_thread.is_alive():
                self.logger.warning("Daemon thread did not stop within timeout")
                return False
        return True

    def _finalize_shutdown(self) -> None:
        """Invoke ``application.cleanup()`` at most once per daemon lifecycle."""
        if self._cleaned_up:
            return
        self._cleaned_up = True
        if hasattr(self.application, "cleanup"):
            try:
                self.application.cleanup()
            except Exception as exc:
                self.logger.warning(f"Application cleanup failed: {exc}")
