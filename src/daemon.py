#!/usr/bin/env python3
"""Daemon management module for background process operation.

This module provides the DaemonManager class for running applications as
background services with proper signal handling, periodic execution,
and graceful shutdown support.

Typical usage:
    >>> daemon = DaemonManager(app, config, logger)
    >>> daemon.start()  # Background thread
    >>> # Or:
    >>> daemon.run_forever()  # Foreground blocking

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

# Standard Imports
import signal
import threading
import time
import sys
from typing import Optional, Dict, Any

# Local Imports
from src.core.constants import DaemonDefaults

################################################################################
# DAEMON MANAGER CLASS - Background Process Management
################################################################################

class DaemonManager:
    """Daemon manager for background process operation.

    Handles signal management (SIGTERM, SIGINT, SIGHUP), periodic execution
    of application cycles, and graceful shutdown with timeout.

    Attributes:
        application: Application instance with run_cycle() method.
        config: Configuration object.
        logger: Logger instance.
        running: Whether daemon is currently running.
    """

    def __init__(self, application: Any, config: Any, logger: Any) -> None:
        """Initialize daemon manager.

        Args:
            application: Application instance with run_cycle() method.
            config: Configuration object with daemon settings.
            logger: Logger instance for daemon logging.
        """
        self.application = application
        self.config = config
        self.logger = logger
        
        self.running = False
        self._stop_event = threading.Event()
        self._daemon_thread: Optional[threading.Thread] = None
        
        self._setup_signal_handlers()
        self.logger.debug("Daemon manager initialized")


    ################################################################################
    # PUBLIC INTERFACE - Daemon Lifecycle Management
    ################################################################################

    def start(self) -> bool:
        """Start the daemon in a background thread.

        Returns:
            True if started successfully, False if already running.
        """
        if self.running:
            self.logger.warning("Daemon is already running")
            return False
            
        self.logger.info("Starting daemon...")
        
        try:
            self.running = True
            self._stop_event.clear()
            
            self._daemon_thread = threading.Thread(
                target=self._daemon_loop,
                name="DaemonLoop",
                daemon=False
            )
            self._daemon_thread.start()
            
            self.logger.info("Daemon started successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start daemon: {e}")
            self.running = False
            return False


    def stop(self) -> bool:
        """Stop the daemon gracefully.

        Waits up to 30 seconds for the daemon thread to finish.

        Returns:
            True if stopped successfully, False if not running or timeout.
        """
        if not self.running:
            self.logger.warning("Daemon is not running")
            return False
            
        self.logger.info("Stopping daemon...")
        
        try:
            self._stop_event.set()
            self.running = False
            
            if self._daemon_thread and self._daemon_thread.is_alive():
                self.logger.debug("Waiting for daemon thread to finish...")
                self._daemon_thread.join(timeout=DaemonDefaults.STOP_TIMEOUT)
                
                if self._daemon_thread.is_alive():
                    self.logger.warning("Daemon thread did not stop within timeout")
                    return False
                    
            if hasattr(self.application, 'cleanup'):
                try:
                    self.application.cleanup()
                except Exception as e:
                    self.logger.warning(f"Application cleanup failed: {e}")
                    
            self.logger.info("Daemon stopped successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error stopping daemon: {e}")
            return False


    def run_forever(self) -> None:
        """Run daemon in foreground mode as a blocking call.

        Starts the daemon loop in the current thread instead of spawning
        a background thread. Handles keyboard interrupts gracefully.

        Raises:
            Exception: Re-raises any exception from the daemon loop.
        """
        self.logger.debug("Starting daemon in foreground mode...")
        
        try:
            self.running = True
            self._stop_event.clear()
            self._daemon_loop()
            
        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt, stopping...")
            self.stop()
        except Exception as e:
            self.logger.error(f"Daemon error: {e}")
            raise
        finally:
            self.running = False


    ################################################################################
    # PUBLIC INTERFACE - Status and Information
    ################################################################################

    def is_running(self) -> bool:
        """Check if the daemon is currently running.

        Returns:
            True if the daemon is active and no stop has been requested,
            False otherwise.
        """
        return self.running and not self._stop_event.is_set()


    def get_status(self) -> Dict[str, Any]:
        """Get current daemon status information.

        Returns:
            Dictionary containing running state, stop request status,
            thread alive status, cycle interval, and application state.
        """
        return {
            'running': self.running,
            'stop_requested': self._stop_event.is_set(),
            'thread_alive': self._daemon_thread.is_alive() if self._daemon_thread else False,
            'cycle_interval': self.config.daemon_check_interval,
            'application_running': self.application.is_running() if hasattr(self.application, 'is_running') else None
        }


    ################################################################################
    # PRIVATE METHODS - Internal Implementation
    ################################################################################

    def _setup_signal_handlers(self) -> None:
        """Setup Unix signal handlers for graceful shutdown and reload.

        Registers handlers for SIGTERM, SIGINT (graceful shutdown) and
        SIGHUP (configuration reload).
        """
        def signal_handler(signum: int, frame: Any) -> None:
            """Handle termination signals (SIGINT, SIGTERM) by initiating shutdown.

            Args:
                signum: The signal number received.
                frame: The current stack frame.
            """
            self.logger.info(f"Received signal {signum}, initiating shutdown...")
            self.stop()
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        def reload_handler(signum: int, frame: Any) -> None:
            """Handle SIGHUP by reloading the application configuration.

            Args:
                signum: The signal number received.
                frame: The current stack frame.
            """
            self.logger.info("Received SIGHUP, reloading configuration...")
            try:
                if hasattr(self.application, 'reload_config'):
                    self.application.reload_config()
                else:
                    self.logger.warning("Application does not support config reload")
            except Exception as e:
                self.logger.error(f"Failed to reload configuration: {e}")
                
        signal.signal(signal.SIGHUP, reload_handler)


    def _daemon_loop(self) -> None:
        """Main daemon loop that executes application cycles at intervals.

        Runs the application's run_cycle method at regular intervals defined
        by the configuration. Handles timing to maintain consistent intervals.
        """
        self.logger.debug(f"Daemon loop started (interval: {self.config.daemon_check_interval}s)")
        
        while self.running and not self._stop_event.is_set():
            try:
                cycle_start_time = time.time()
                
                if hasattr(self.application, 'run_cycle'):
                    success = self.application.run_cycle()
                    if not success:
                        self.logger.warning("Application cycle returned failure")
                else:
                    self.logger.warning("Application does not have run_cycle method")
                
                cycle_duration = time.time() - cycle_start_time
                sleep_time = max(0, self.config.daemon_check_interval - cycle_duration)
                
                if sleep_time > 0:
                    self.logger.debug(f"Cycle completed in {cycle_duration:.2f}s, sleeping for {sleep_time:.2f}s")
                    if self._stop_event.wait(timeout=sleep_time):
                        break
                else:
                    self.logger.warning(f"Cycle took {cycle_duration:.2f}s, longer than interval {self.config.daemon_check_interval}s")
                    
            except Exception as e:
                self.logger.error(f"Error in daemon loop: {e}")
                if not self._stop_event.wait(timeout=self.config.daemon_retry_delay):
                    continue
                else:
                    break
                    
        self.logger.debug("Daemon loop finished")