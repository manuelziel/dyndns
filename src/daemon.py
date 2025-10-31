#!/usr/bin/env python3
"""
Daemon Management Module

Contains daemon functionality for background operation with proper
signal handling, process management, and error recovery.

Created: 2025-10-27
Author: Manuel Ziel
License: MIT

This program is free software: you can redistribute it and/or modify
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

# Standard library imports
import os
import signal
import sys
import threading
import time
from typing import Optional, Callable, Dict, Any

################################################################################
# DAEMON MANAGER CLASS - Background Process Management
################################################################################

class DaemonManager:
    """Daemon manager for background operation with signal handling and graceful shutdown."""
    
    def __init__(self, application: Any, config: Any, logger: Any, cycle_interval: int = 60) -> None:
        """Initialize daemon manager."""
        self.application = application
        self.config = config
        self.logger = logger
        self.cycle_interval = cycle_interval
        
        self.running = False
        self._stop_event = threading.Event()
        self._daemon_thread: Optional[threading.Thread] = None
        
        self._setup_signal_handlers()
        self.logger.debug("Daemon manager initialized")

    ################################################################################
    # PUBLIC INTERFACE - Daemon Lifecycle Management
    ################################################################################

    def start(self) -> bool:
        """Start the daemon in a background thread."""
        if self.running:
            self.logger.warning("Daemon is already running")
            return False
            
        self.logger.info("Starting daemon...")
        
        try:
            self.running = True
            self._stop_event.clear()
            
            # Start daemon thread
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
        """Stop the daemon gracefully."""
        if not self.running:
            self.logger.warning("Daemon is not running")
            return False
            
        self.logger.info("Stopping daemon...")
        
        try:
            self._stop_event.set()
            self.running = False
            
            if self._daemon_thread and self._daemon_thread.is_alive():
                self.logger.debug("Waiting for daemon thread to finish...")
                self._daemon_thread.join(timeout=30)  # 30 second timeout
                
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
        """Run daemon in foreground (blocking call)."""
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
        """Check if daemon is currently running."""
        return self.running and not self._stop_event.is_set()

    def get_status(self) -> Dict[str, Any]:
        """Get current daemon status information."""
        return {
            'running': self.running,
            'stop_requested': self._stop_event.is_set(),
            'thread_alive': self._daemon_thread.is_alive() if self._daemon_thread else False,
            'cycle_interval': self.cycle_interval,
            'application_running': self.application.is_running() if hasattr(self.application, 'is_running') else None
        }

    ################################################################################
    # PRIVATE METHODS - Internal Implementation
    ################################################################################

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum: int, frame: Any) -> None:
            self.logger.info(f"Received signal {signum}, initiating shutdown...")
            self.stop()
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        def reload_handler(signum: int, frame: Any) -> None:
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
        """Main daemon loop that executes application cycles at regular intervals."""
        self.logger.debug(f"Daemon loop started (interval: {self.cycle_interval}s)")
        
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
                sleep_time = max(0, self.cycle_interval - cycle_duration)
                
                if sleep_time > 0:
                    self.logger.debug(f"Cycle completed in {cycle_duration:.2f}s, sleeping for {sleep_time:.2f}s")
                    if self._stop_event.wait(timeout=sleep_time):
                        break
                else:
                    self.logger.warning(f"Cycle took {cycle_duration:.2f}s, longer than interval {self.cycle_interval}s")
                    
            except Exception as e:
                self.logger.error(f"Error in daemon loop: {e}")
                if not self._stop_event.wait(timeout=10):
                    continue
                else:
                    break
                    
        self.logger.debug("Daemon loop finished")