"""Batch image processing service for efficient multi-image classification.

Processes multiple images concurrently using ThreadPoolExecutor,
useful for wardrobe imports or batch uploads.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from app.ml.image_recognizer import ImageRecognizer, RecognitionResult

logger = logging.getLogger(__name__)

# Default thread pool size for batch processing
DEFAULT_BATCH_WORKERS = 4
MAX_BATCH_SIZE = 100


class BatchProcessor:
    """Process multiple images concurrently."""

    def __init__(self, max_workers: int = DEFAULT_BATCH_WORKERS):
        """Initialize batch processor.

        Args:
            max_workers: Maximum number of concurrent worker threads
        """
        self.max_workers = min(max_workers, DEFAULT_BATCH_WORKERS)
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.recognizer = ImageRecognizer()

    def process_batch(
        self, image_bytes_list: List[bytes], timeout_sec: float = 30.0
    ) -> List[Optional[RecognitionResult]]:
        """Process a batch of images concurrently.

        Args:
            image_bytes_list: List of image byte strings (max 100 images)
            timeout_sec: Timeout in seconds for entire batch

        Returns:
            List of RecognitionResult or None for each image
        """
        if len(image_bytes_list) > MAX_BATCH_SIZE:
            raise ValueError(f"Batch size {len(image_bytes_list)} exceeds max {MAX_BATCH_SIZE}")

        # Submit all tasks to executor
        futures = [
            self.executor.submit(self._process_single, img_bytes) for img_bytes in image_bytes_list
        ]

        # Collect results with timeout
        results = []
        for future in futures:
            try:
                result = future.result(timeout=timeout_sec / len(image_bytes_list))
                results.append(result)
            except Exception as e:
                logger.warning(f"Image processing failed: {e}")
                results.append(None)

        return results

    def _process_single(self, image_bytes: bytes) -> Optional[RecognitionResult]:
        """Process a single image (runs in executor thread).

        Args:
            image_bytes: Raw image data

        Returns:
            RecognitionResult or None on failure
        """
        try:
            return self.recognizer.recognize(image_bytes)
        except Exception as e:
            logger.error(f"Recognition failed: {e}")
            return None

    def close(self):
        """Shutdown executor and cleanup resources."""
        if self.executor:
            self.executor.shutdown(wait=False)


# Singleton instance
_batch_processor: Optional[BatchProcessor] = None


def get_batch_processor(max_workers: int = DEFAULT_BATCH_WORKERS) -> BatchProcessor:
    """Get or create singleton batch processor.

    Args:
        max_workers: Max worker threads (only used on first call)

    Returns:
        BatchProcessor instance
    """
    global _batch_processor
    if _batch_processor is None:
        _batch_processor = BatchProcessor(max_workers=max_workers)
    return _batch_processor
