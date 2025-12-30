"""
Utility Functions for Triton Spark TTS + RVC Pipeline

Helper functions for:
- Temp directory management
- Text splitting
- CUDA stream initialization
- Queue/event creation
"""

import os
import re
import shutil
import threading
import logging
from queue import PriorityQueue, Queue

import torch

from rvc.processing.buffer_queue import OrderedAudioBufferQueue

logger = logging.getLogger(__name__)


def initialize_temp_dirs():
    """
    Initialize temporary directories for TTS and RVC outputs.
    Clears any existing files from previous runs.
    """
    temp_dirs = ["./TEMP/spark", "./TEMP/rvc"]

    for dir_path in temp_dirs:
        os.makedirs(dir_path, exist_ok=True)

        # Clean up existing files
        for filename in os.listdir(dir_path):
            file_path = os.path.join(dir_path, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                    logger.debug(f"Removed file: {file_path}")
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                    logger.debug(f"Removed directory: {file_path}")
            except Exception as e:
                logger.error(f"Failed to delete {file_path}: {e}")


def prepare_audio_buffer(buffer_time: float = 1.0) -> OrderedAudioBufferQueue:
    """
    Create and return an OrderedAudioBufferQueue for managing audio output order.

    Args:
        buffer_time: Buffer time between audio files in seconds.

    Returns:
        OrderedAudioBufferQueue instance.
    """
    return OrderedAudioBufferQueue(buffer_time)


def split_into_sentences(text: str) -> list:
    """
    Split text into sentences using regular expressions.

    Args:
        text: The input text to split.

    Returns:
        List of sentences.
    """
    # Split on period, exclamation mark, or question mark followed by space or end of string
    sentences = re.split(r"(?<=[.!?])\s+|(?<=[.!?])$", text)
    # Remove any empty sentences
    sentences = [s.strip() for s in sentences if s.strip()]
    return sentences


def split_text_and_validate(text: str) -> list:
    """
    Split text into sentences and validate.

    Args:
        text: Input text to process.

    Returns:
        List of sentences.

    Raises:
        ValueError: If no valid text to process.
    """
    sentences = split_into_sentences(text)
    if not sentences:
        raise ValueError("No valid text to process.")
    return sentences


def get_base_fragment_num(sentences: list) -> int:
    """
    Get a base fragment number that doesn't conflict with existing files.

    Args:
        sentences: List of sentences to process.

    Returns:
        Base fragment number to use.
    """
    base_fragment_num = 1
    while any(
        os.path.exists(f"./TEMP/spark/fragment_{base_fragment_num + i}.wav")
        or os.path.exists(f"./TEMP/rvc/fragment_{base_fragment_num + i}.wav")
        for i in range(len(sentences))
    ):
        base_fragment_num += 1
    return base_fragment_num


def prepare_prompt(
    prompt_wav_upload: str,
    prompt_wav_record: str,
    prompt_text: str,
) -> tuple:
    """
    Prepare prompt audio and text for TTS.

    Args:
        prompt_wav_upload: Path to uploaded prompt audio.
        prompt_wav_record: Path to recorded prompt audio.
        prompt_text: Transcript of prompt audio.

    Returns:
        Tuple of (prompt_speech_path, prompt_text_clean).
    """
    prompt_speech = prompt_wav_upload if prompt_wav_upload else prompt_wav_record
    prompt_text_clean = None if not prompt_text or len(prompt_text) < 2 else prompt_text
    return prompt_speech, prompt_text_clean


def initialize_cuda_streams(num_tts_workers: int, num_rvc_workers: int) -> tuple:
    """
    Initialize CUDA streams for workers.

    For Triton architecture:
    - TTS workers don't need streams (Triton handles GPU)
    - RVC workers use streams for parallel inference

    Args:
        num_tts_workers: Number of TTS workers (unused, kept for API compatibility).
        num_rvc_workers: Number of RVC workers.

    Returns:
        Tuple of (tts_streams, rvc_streams).
    """
    use_cuda = torch.cuda.is_available()

    # TTS workers don't need CUDA streams with Triton
    tts_streams = [None] * num_tts_workers

    if use_cuda:
        rvc_streams = [torch.cuda.Stream() for _ in range(num_rvc_workers)]
        logger.info(f"Created {num_rvc_workers} CUDA streams for RVC workers")
    else:
        rvc_streams = [None] * num_rvc_workers
        logger.warning("CUDA not available, RVC parallel processing will be limited")

    return tts_streams, rvc_streams


def create_queues_and_events(num_tts_workers: int, num_rvc_workers: int) -> tuple:
    """
    Create queues and events for inter-worker communication.

    Args:
        num_tts_workers: Number of TTS workers.
        num_rvc_workers: Number of RVC workers.

    Returns:
        Tuple of (tts_to_rvc_queue, rvc_results_queue, tts_complete_events,
                  rvc_complete_events, processing_complete).
    """
    tts_to_rvc_queue = Queue()
    rvc_results_queue = Queue()
    tts_complete_events = [threading.Event() for _ in range(num_tts_workers)]
    rvc_complete_events = [threading.Event() for _ in range(num_rvc_workers)]
    processing_complete = threading.Event()

    return (
        tts_to_rvc_queue,
        rvc_results_queue,
        tts_complete_events,
        rvc_complete_events,
        processing_complete,
    )


def create_sentence_priority_queue(sentences: list) -> tuple:
    """
    Creates a priority queue of sentences, prioritized by their original order.

    Args:
        sentences: List of sentences to process.

    Returns:
        Tuple of (priority_queue, sentence_count).
    """
    sentence_queue = PriorityQueue()
    for idx, sentence in enumerate(sentences):
        # Use index as priority to maintain original order
        sentence_queue.put((idx, idx, sentence))

    return sentence_queue, len(sentences)
