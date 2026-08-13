#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Regression tests for CRLF-expanded binary MAVLink serial receivers."""

import unittest

from pymavlink.dialects.v20 import common as mavlink

from dronecot.classes import (
    SerialWorker,
    _CRLFNormalizer,
    _CRLFNormalizingReceiver,
)


class CRLFNormalizerTest(unittest.TestCase):
    """Exercise the streaming inverse of ESP console newline expansion."""

    def test_reverses_expansion_across_every_chunk_boundary(self):
        original = b"header\nbody\r\ntail\x00\nend"
        expanded = original.replace(b"\n", b"\r\n")

        for split in range(len(expanded) + 1):
            normalizer = _CRLFNormalizer()
            actual = normalizer.feed(expanded[:split])
            actual += normalizer.feed(expanded[split:])
            self.assertEqual(actual, original, f"split={split}")

    def test_preserves_a_cr_not_followed_by_lf(self):
        normalizer = _CRLFNormalizer()
        self.assertEqual(normalizer.feed(b"one\r"), b"one")
        self.assertEqual(normalizer.feed(b"two"), b"\rtwo")

    def test_receiver_wrapper_preserves_state_between_reads(self):
        chunks = iter((b"abc\r", b"\ndef", b""))
        receiver = _CRLFNormalizingReceiver(lambda _size: next(chunks))
        self.assertEqual(receiver(4), b"abc")
        self.assertEqual(receiver(4), b"\ndef")
        self.assertEqual(receiver(4), b"")

    def test_recovers_checksum_valid_mavlink_frame(self):
        encoder = mavlink.MAVLink(None, srcSystem=254, srcComponent=236)
        # custom_mode=10 guarantees an LF byte inside the binary payload.
        packet = encoder.heartbeat_encode(34, 8, 0, 10, 4, 3).pack(encoder)
        self.assertIn(b"\n", packet)
        expanded = (packet + b"\n").replace(b"\n", b"\r\n")

        normalizer = _CRLFNormalizer()
        recovered = b"".join(normalizer.feed(bytes((byte,))) for byte in expanded)
        self.assertEqual(recovered, packet + b"\n")

        parser = mavlink.MAVLink(None)
        parser.robust_parsing = True
        messages = []
        for byte in recovered:
            message = parser.parse_char(bytes((byte,)))
            if message is not None and message.get_type() != "BAD_DATA":
                messages.append(message)

        self.assertEqual([message.get_type() for message in messages], ["HEARTBEAT"])
        self.assertEqual(messages[0].custom_mode, 10)


class SerialWorkerCRLFConfigTest(unittest.TestCase):
    """Keep the compatibility filter opt-in for standards-compliant feeds."""

    @staticmethod
    def _worker(value=None):
        worker = SerialWorker.__new__(SerialWorker)
        worker.config = {}
        if value is not None:
            worker.config["SERIAL_CRLF_NORMALIZE"] = value
        return worker

    def test_disabled_by_default(self):
        self.assertFalse(self._worker()._serial_crlf_normalization_enabled())

    def test_accepts_common_true_values(self):
        for value in ("1", "true", "TRUE", "yes", "on", 1, True):
            with self.subTest(value=value):
                self.assertTrue(
                    self._worker(value)._serial_crlf_normalization_enabled()
                )

    def test_rejects_false_values(self):
        for value in ("0", "false", "no", "off", "", 0, False):
            with self.subTest(value=value):
                self.assertFalse(
                    self._worker(value)._serial_crlf_normalization_enabled()
                )


if __name__ == "__main__":
    unittest.main()
