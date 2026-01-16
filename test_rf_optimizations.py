#!/usr/bin/env python3
"""
Test suite for RF Connection System Optimizations
Tests the server-side improvements for robust RF connections
"""

import sys
import os
import socket
import select  # ✅ Agregado import faltante
import time
import threading
import unittest
from unittest.mock import Mock, patch, MagicMock

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the modules to test
try:
    from audio_server.native_server import NativeClient, NativeServer
    from audio_server.native_protocol import NativeAndroidProtocol
    print("✅ Successfully imported native_server modules")
    MODULES_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Native modules not available: {e}")
    print("   Running tests with mocked components")
    MODULES_AVAILABLE = False

    # Create mock classes for testing
    class MockNativeClient:
        def __init__(self, client_id, sock, address):
            self.id = client_id
            self.socket = sock
            self.address = address
            self.status = 1
            self.last_activity = time.time()
            self.consecutive_send_failures = 0
            self.max_consecutive_failures = 10
            self.first_buffer_full_time = None

        def _is_socket_really_alive(self, sock):
            """Mock implementation of the optimized socket check"""
            if sock is None:
                return False
            try:
                if sock.fileno() == -1:
                    return False
                # Mock select call
                readable, writable, errors = select.select([], [sock], [sock], 0)
                if errors:
                    return False
                # Mock peek
                sock.setblocking(False)
                try:
                    data = sock.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT)
                    if len(data) == 0:
                        return False
                except BlockingIOError:
                    pass
                except (ConnectionError, OSError):
                    return False
                finally:
                    sock.setblocking(False)
                return True
            except (OSError, ValueError, AttributeError):
                return False

        def is_alive(self, timeout=30.0, buffer_grace=30.0):
            """Mock implementation of the optimized is_alive"""
            if self.status == 0:
                return False
            if not self._is_socket_really_alive(self.socket):
                return False
            time_since_activity = time.time() - self.last_activity
            if time_since_activity > timeout:
                return False
            if self.consecutive_send_failures >= self.max_consecutive_failures:
                if self.first_buffer_full_time is None:
                    self.first_buffer_full_time = time.time()
                elif time.time() - self.first_buffer_full_time > buffer_grace:
                    return False
            else:
                self.first_buffer_full_time = None
            return True

    class MockNativeServer:
        def __init__(self):
            self.clients = {}
            self.persistent_lock = threading.Lock()  # ✅ Agregado atributo faltante

        def _is_socket_really_alive(self, sock):
            """Mock implementation"""
            return True  # ✅ Agregado método faltante

        def _sync_to_magic(self, sock, timeout=1.0):
            """Mock implementation of optimized sync_to_magic"""
            MAGIC_BYTES = b'\xA1\xD1\x0A\x7C'
            MAX_SCAN_BYTES = 4096

            buffer = bytearray()
            start = time.time()
            bytes_scanned = 0

            try:
                sock.setblocking(False)
                while time.time() - start < timeout and bytes_scanned < MAX_SCAN_BYTES:
                    try:
                        chunk = sock.recv(64)
                        if not chunk:
                            return None
                        buffer.extend(chunk)
                        bytes_scanned += len(chunk)

                        for i in range(max(0, len(buffer) - len(chunk) - 3), len(buffer) - 3):
                            if buffer[i:i+4] == MAGIC_BYTES:
                                remaining = 12 - (len(buffer) - i - 4)
                                if remaining > 0:
                                    rest = sock.recv(remaining)
                                    if len(rest) != remaining:
                                        continue
                                    buffer.extend(rest)
                                header_start = i
                                return bytes(buffer[header_start:header_start + 16])
                        if len(buffer) > 1024:
                            buffer = buffer[-256:]
                    except BlockingIOError:
                        time.sleep(0.001)
                        continue
                    except (ConnectionError, OSError):
                        return None
            finally:
                sock.setblocking(False)
            return None

        def _handle_control_message(self, client, message):
            """Mock implementation of control message handling"""
            msg_type = message.get('type', '')
            if msg_type == 'handshake_ack':
                client.handshake_acked = True

        def _disconnect_client(self, client_id, preserve_state=False):
            """Mock implementation of optimized disconnect"""
            client = self.clients.pop(client_id, None)
            if client:
                client.status = 0
                if client.socket:
                    try:
                        client.socket.settimeout(0.5)
                        client.socket.shutdown(socket.SHUT_RDWR)
                    except:
                        pass
                    try:
                        client.socket.close()
                    except:
                        pass
                    client.socket = None

    # Use mock classes
    NativeClient = MockNativeClient
    NativeServer = MockNativeServer

class TestNativeClientOptimizations(unittest.TestCase):
    """Test the optimized NativeClient methods"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_socket = Mock()
        self.mock_socket.fileno.return_value = 123
        self.mock_socket.setblocking = Mock()
        self.mock_socket.recv = Mock()

        self.client = NativeClient("test_client", self.mock_socket, ("127.0.0.1", 5101))

    def test_is_socket_really_alive_valid_socket(self):
        """Test _is_socket_really_alive with valid socket"""
        # Mock select to return socket in writable
        with patch('select.select') as mock_select:
            mock_select.return_value = ([], [self.mock_socket], [])

            # Mock recv to return data (not EOF)
            self.mock_socket.recv.return_value = b'data'

            result = self.client._is_socket_really_alive(self.mock_socket)
            self.assertTrue(result)

    def test_is_socket_really_alive_eof(self):
        """Test _is_socket_really_alive detects EOF"""
        with patch('select.select') as mock_select:
            mock_select.return_value = ([], [self.mock_socket], [])

            # Mock recv to return empty bytes (EOF)
            self.mock_socket.recv.return_value = b''

            result = self.client._is_socket_really_alive(self.mock_socket)
            self.assertFalse(result)

    def test_is_socket_really_alive_closed_socket(self):
        """Test _is_socket_really_alive with closed socket"""
        self.mock_socket.fileno.return_value = -1

        result = self.client._is_socket_really_alive(self.mock_socket)
        self.assertFalse(result)

    def test_is_socket_really_alive_select_error(self):
        """Test _is_socket_really_alive with select error"""
        with patch('select.select') as mock_select:
            mock_select.return_value = ([], [], [self.mock_socket])  # errors list

            result = self.client._is_socket_really_alive(self.mock_socket)
            self.assertFalse(result)

    def test_is_alive_with_dead_socket(self):
        """Test is_alive detects dead socket first"""
        self.client.status = 1
        self.client.last_activity = time.time()

        with patch.object(self.client, '_is_socket_really_alive', return_value=False):
            result = self.client.is_alive()
            self.assertFalse(result)

    def test_is_alive_with_timeout(self):
        """Test is_alive detects activity timeout"""
        self.client.status = 1
        self.client.last_activity = time.time() - 40  # 40 seconds ago

        with patch.object(self.client, '_is_socket_really_alive', return_value=True):
            result = self.client.is_alive(timeout=30.0)
            self.assertFalse(result)

    def test_is_alive_with_buffer_stuck(self):
        """Test is_alive detects stuck buffer"""
        self.client.status = 1
        self.client.last_activity = time.time()
        self.client.consecutive_send_failures = 15
        self.client.first_buffer_full_time = time.time() - 40  # 40 seconds ago

        with patch.object(self.client, '_is_socket_really_alive', return_value=True):
            result = self.client.is_alive(buffer_grace=30.0)
            self.assertFalse(result)

class TestNativeServerOptimizations(unittest.TestCase):
    """Test the optimized NativeServer methods"""

    def setUp(self):
        """Set up test fixtures"""
        self.server = NativeServer()
        self.mock_socket = Mock()
        self.mock_socket.fileno.return_value = 456

    def test_sync_to_magic_with_limit(self):
        """Test _sync_to_magic respects byte limit"""
        # Create a socket that returns data byte by byte
        self.mock_socket.recv = Mock(side_effect=[b'x'] * 4097)  # More than MAX_SCAN_BYTES

        start_time = time.time()
        result = self.server._sync_to_magic(self.mock_socket, timeout=0.1)
        elapsed = time.time() - start_time

        # Should timeout quickly due to byte limit
        self.assertIsNone(result)
        self.assertLess(elapsed, 0.5)  # Should not take full timeout

    def test_sync_to_magic_finds_magic(self):
        """Test _sync_to_magic finds MAGIC number"""
        magic_bytes = b'\xA1\xD1\x0A\x7C'  # NativeAndroidProtocol.MAGIC_NUMBER
        test_data = b'junk' + magic_bytes + b'\x00' * 12  # MAGIC + 12 bytes header

        call_count = 0
        def recv_side_effect(size):
            nonlocal call_count
            if call_count < len(test_data):
                result = test_data[call_count:call_count+1]
                call_count += 1
                return result
            return b''

        self.mock_socket.recv = Mock(side_effect=recv_side_effect)

        result = self.server._sync_to_magic(self.mock_socket, timeout=1.0)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 16)  # Full header

class TestHandshakeACK(unittest.TestCase):
    """Test handshake ACK functionality"""

    def setUp(self):
        self.server = NativeServer()
        self.mock_client = Mock()
        self.mock_client.id = "test_client"
        self.mock_client.handshake_acked = False

    def test_handshake_ack_sets_flag(self):
        """Test that handshake_ack message sets the flag"""
        message = {'type': 'handshake_ack'}

        # Mock the logger to avoid output
        with patch('audio_server.native_server.logger'):
            self.server._handle_control_message(self.mock_client, message)

        self.assertTrue(self.mock_client.handshake_acked)

class TestDisconnectOptimizations(unittest.TestCase):
    """Test the optimized disconnect functionality"""

    def setUp(self):
        self.server = NativeServer()
        self.mock_client = Mock()
        self.mock_client.id = "test_client"
        self.mock_client.status = 1
        self.mock_client.socket = Mock()
        self.mock_client.auto_reconnect = True

    @patch('audio_server.native_server.logger')
    def test_disconnect_minimal_lock_time(self, mock_logger):
        """Test that _disconnect_client uses minimal lock time"""
        # Mock the client dictionary
        self.server.clients = {"test_client": self.mock_client}

        # Mock the persistent lock and state
        with patch.object(self.server, 'persistent_lock'), \
             patch.object(self.server, 'channel_manager'), \
             patch.object(self.server, 'audio_send_pool') as mock_pool:

            # Mock the client's close method
            self.mock_client.close = Mock()

            self.server._disconnect_client("test_client", preserve_state=True)

            # Verify client was removed from dictionary
            self.assertNotIn("test_client", self.server.clients)

            # Verify socket operations were called
            self.mock_client.socket.settimeout.assert_called_with(0.5)
            self.mock_client.socket.shutdown.assert_called()
            self.mock_client.socket.close.assert_called()

            # Verify async cleanup was scheduled
            mock_pool.submit.assert_called()

def run_performance_test():
    """Run performance test for the optimized methods"""
    print("\n🧪 Running Performance Tests...")

    server = NativeServer()

    # Test socket alive check performance
    mock_socket = Mock()
    mock_socket.fileno.return_value = 123

    with patch('select.select', return_value=([], [mock_socket], [])):
        mock_socket.recv.return_value = b'data'

        start_time = time.time()
        for _ in range(1000):
            server._is_socket_really_alive(mock_socket)
        elapsed = time.time() - start_time

        print(f"   1000 socket checks took {elapsed:.4f} seconds")
        print(f"   Average time per check: {elapsed/1000:.2f} ms")
        if elapsed < 0.1:
            print("✅ Performance test PASSED")
        else:
            print("⚠️ Performance test SLOW - may need optimization")

def main():
    """Run all tests"""
    print("🚀 Starting RF Connection System Tests")
    print("=" * 50)

    # Run unit tests
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestNativeClientOptimizations))
    suite.addTests(loader.loadTestsFromTestCase(TestNativeServerOptimizations))
    suite.addTests(loader.loadTestsFromTestCase(TestHandshakeACK))
    suite.addTests(loader.loadTestsFromTestCase(TestDisconnectOptimizations))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Run performance test
    run_performance_test()

    # Summary
    print("\n" + "=" * 50)
    if result.wasSuccessful():
        print("✅ ALL TESTS PASSED!")
        print(f"   Ran {result.testsRun} tests successfully")
        return 0
    else:
        print("❌ SOME TESTS FAILED!")
        print(f"   Ran {result.testsRun} tests")
        print(f"   Failures: {len(result.failures)}")
        print(f"   Errors: {len(result.errors)}")
        return 1

if __name__ == '__main__':
    sys.exit(main())