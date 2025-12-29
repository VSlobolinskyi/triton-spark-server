"""
Processing Module for Triton Spark TTS + RVC Pipeline

Components:
- workers: Persistent TTS and RVC worker threads
- worker_manager: Worker lifecycle management
- buffer_queue: Ordered audio output buffering
- utils: Helper functions
"""

from rvc.processing.workers import persistent_tts_worker, persistent_rvc_worker
from rvc.processing.worker_manager import (
    WorkerManager,
    get_worker_manager,
    set_worker_unload_delay,
    get_current_worker_unload_delay,
)
from rvc.processing.buffer_queue import AudioBufferQueue, OrderedAudioBufferQueue
from rvc.processing.utils import (
    initialize_temp_dirs,
    prepare_audio_buffer,
    split_into_sentences,
    split_text_and_validate,
    get_base_fragment_num,
    prepare_prompt,
    initialize_cuda_streams,
    create_queues_and_events,
    create_sentence_priority_queue,
)

__all__ = [
    # Workers
    "persistent_tts_worker",
    "persistent_rvc_worker",
    # Manager
    "WorkerManager",
    "get_worker_manager",
    "set_worker_unload_delay",
    "get_current_worker_unload_delay",
    # Buffer
    "AudioBufferQueue",
    "OrderedAudioBufferQueue",
    # Utils
    "initialize_temp_dirs",
    "prepare_audio_buffer",
    "split_into_sentences",
    "split_text_and_validate",
    "get_base_fragment_num",
    "prepare_prompt",
    "initialize_cuda_streams",
    "create_queues_and_events",
    "create_sentence_priority_queue",
]
