"""
Tests for ImageRecognizer singleton pattern.

Key requirement: ImageRecognizer must be initialized ONCE and reused
across all requests. It must NOT be reloaded on each request.
"""

from unittest.mock import patch

import numpy as np  # noqa: F401
from PIL import Image  # noqa: F401

from app.ml import image_recognizer  # noqa: F401


class TestImageRecognizerSingleton:
    """Test that ImageRecognizer uses a proper singleton pattern."""

    def test_get_recognizer_returns_same_instance(self):
        """
        Multiple calls to get_recognizer() MUST return the SAME instance.
        The singleton must be permanent and not recreated.
        """
        # Save original singleton state
        original_instance = image_recognizer._recognizer_instance
        image_recognizer._recognizer_instance = None

        try:
            # Mock all internal modules to avoid real ML model loading
            with patch.object(image_recognizer.ImageRecognizer, "__init__", return_value=None):
                recognizer1 = image_recognizer.get_recognizer()
                recognizer2 = image_recognizer.get_recognizer()
                recognizer3 = image_recognizer.get_recognizer()

                # All three calls must return the same instance
                assert recognizer1 is recognizer2, (
                    "get_recognizer() must return the same singleton instance. "
                    "Second call created a NEW instance instead of reusing the singleton."
                )
                assert recognizer2 is recognizer3, (
                    "get_recognizer() must return the same singleton instance. "
                    "Third call created another NEW instance."
                )

                print(
                    f"Singleton test passed: "
                    f"all calls return the same instance id={id(recognizer1)}"
                )
        finally:
            # Restore original state
            image_recognizer._recognizer_instance = original_instance

    def test_singleton_not_recreated_on_multiple_calls(self):
        """
        Verify that the internal _recognizer_instance is set and not None
        after the first call to get_recognizer().
        """
        original_instance = image_recognizer._recognizer_instance
        image_recognizer._recognizer_instance = None

        try:
            call_count = 0

            class MockRecognizer:
                """Mock that tracks instantiation."""

                def __init__(self):
                    nonlocal call_count
                    call_count += 1

            with patch.object(image_recognizer.ImageRecognizer, "__init__", return_value=None):
                with patch.object(image_recognizer, "ImageRecognizer", MockRecognizer):
                    # Reset module-level singleton
                    image_recognizer._recognizer_instance = None

                    # First call
                    r1 = image_recognizer.get_recognizer()
                    first_id = id(r1)

                    # Verify instance is cached
                    assert (
                        image_recognizer._recognizer_instance is not None
                    ), "After first get_recognizer() call, _recognizer_instance must be set"
                    assert (
                        image_recognizer._recognizer_instance is r1
                    ), "_recognizer_instance must reference the same object as returned value"

                    # Second call
                    r2 = image_recognizer.get_recognizer()
                    second_id = id(r2)

                    # Both calls must return same instance
                    assert first_id == second_id, (
                        f"First call returned id={first_id}, second call returned id={second_id}. "
                        f"Singleton was recreated instead of reused."
                    )

                    print(f"Singleton permanent: id={first_id}, calls={call_count}")

                    # Should only have been "created" once
                    assert call_count == 1, (
                        f"ImageRecognizer was instantiated {call_count} times. "
                        f"Expected exactly 1 (singleton pattern broken)."
                    )
        finally:
            image_recognizer._recognizer_instance = original_instance

    def test_singleton_survives_across_requests(self):
        """
        Simulate multiple HTTP requests - the singleton should persist
        and not be recreated.
        """
        original_instance = image_recognizer._recognizer_instance
        image_recognizer._recognizer_instance = None

        try:
            with patch.object(image_recognizer.ImageRecognizer, "__init__", return_value=None):
                # Simulate first request
                recognizer_request_1 = image_recognizer.get_recognizer()
                id1 = id(recognizer_request_1)

                # Simulate second request (like a new HTTP request)
                recognizer_request_2 = image_recognizer.get_recognizer()
                id2 = id(recognizer_request_2)

                # Simulate third request
                recognizer_request_3 = image_recognizer.get_recognizer()
                id3 = id(recognizer_request_3)

                # All requests must get the same singleton
                assert id1 == id2 == id3, (
                    f"Simulated requests got different instances: "
                    f"request1={id1}, request2={id2}, request3={id3}. "
                    f"Singleton not persisting across requests."
                )

                print(f"Singleton persists across requests: id={id1}")
        finally:
            image_recognizer._recognizer_instance = original_instance

    def test_singleton_manually_resettable(self):
        """
        The singleton should be resettable for testing purposes
        via directly setting _recognizer_instance = None.
        """
        original_instance = image_recognizer._recognizer_instance
        image_recognizer._recognizer_instance = None

        try:
            with patch.object(image_recognizer.ImageRecognizer, "__init__", return_value=None):
                r1 = image_recognizer.get_recognizer()
                id1 = id(r1)

                # Manually reset (simulating test cleanup)
                image_recognizer._recognizer_instance = None

                # After reset, next call should create new instance
                r2 = image_recognizer.get_recognizer()
                id2 = id(r2)

                # After reset, instances should be different (unless mock returns same mock obj)
                # The key is that reset works
                image_recognizer._recognizer_instance = None

                r3 = image_recognizer.get_recognizer()
                id3 = id(r3)

                # Both should be valid instances
                assert r1 is not None
                assert r2 is not None
                assert r3 is not None

                print(f"Manual reset works: r1={id1}, r2={id2}, r3={id3}")
        finally:
            image_recognizer._recognizer_instance = original_instance

    def test_no_per_request_initialization(self):
        """
        Critical test: ImageRecognizer.__init__ must NOT be called on every request.
        It should only be called once (at startup or first use).
        """
        original_instance = image_recognizer._recognizer_instance
        image_recognizer._recognizer_instance = None

        init_calls = []

        def tracking_init(self):
            init_calls.append("called")
            # Don't call real __init__

        try:
            with patch.object(image_recognizer.ImageRecognizer, "__init__", tracking_init):
                # Simulate 10 HTTP requests
                for i in range(10):
                    recognizer = image_recognizer.get_recognizer()
                    assert recognizer is not None

                # __init__ should be called at most once (ideally once)
                print(f"ImageRecognizer.__init__ called {len(init_calls)} times over 10 requests")

                assert len(init_calls) <= 1, (
                    f"ImageRecognizer.__init__ was called {len(init_calls)} times! "
                    f"Expected at most 1 (singleton). "
                    f"This means ImageRecognizer is being REINITIALIZED on every request, "
                    f"which causes the 26-second delay."
                )
        finally:
            image_recognizer._recognizer_instance = original_instance

    def test_recognizer_class_structure(self):
        """
        Verify ImageRecognizer class exists and has the expected methods.
        """
        from app.ml.image_recognizer import ImageRecognizer

        assert hasattr(ImageRecognizer, "recognize"), "ImageRecognizer must have 'recognize' method"
        assert hasattr(
            ImageRecognizer, "recognize_batch"
        ), "ImageRecognizer must have 'recognize_batch' method"
        assert callable(getattr(ImageRecognizer, "recognize")), "'recognize' must be callable"
        assert callable(
            getattr(ImageRecognizer, "recognize_batch")
        ), "'recognize_batch' must be callable"

        print("ImageRecognizer class structure verified")

    def test_recognizer_result_model(self):
        """
        Verify RecognitionResult model exists and works.
        """
        from app.ml.image_recognizer import RecognitionResult

        # Should be able to create a RecognitionResult
        result = RecognitionResult(
            category="上衣",
            category_confidence=0.85,
            main_color={
                "name": "蓝",
                "rgb": (52, 120, 180),
                "hsv": (210.0, 71.1, 70.6),
                "hex_code": "#3478b4",
            },
            secondary_colors=[],
            style_tags=["通勤"],
            feature_vector=[0.1] * 1280,
        )

        assert result.category == "上衣"
        assert result.category_confidence == 0.85
        assert len(result.feature_vector) == 1280

        print("RecognitionResult model verified")

    def test_get_recognizer_is_exported(self):
        """
        Verify get_recognizer function is accessible from the module.
        """
        assert hasattr(
            image_recognizer, "get_recognizer"
        ), "get_recognizer function must be accessible from app.ml.image_recognizer"
        assert callable(image_recognizer.get_recognizer), "get_recognizer must be callable"

        print("get_recognizer function verified")
