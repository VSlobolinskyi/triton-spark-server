"""
Persistent Workers for Triton Spark TTS + RVC Pipeline

Architecture:
- TTS Worker: Uses TritonSparkClient (gRPC to container), no CUDA stream needed
- RVC Workers: Use CUDA streams for parallel inference on host GPU

Flow:
    [TTS Worker] → tts_to_rvc_queue → [RVC Worker 1 (stream)]
                                   → [RVC Worker 2 (stream)]
"""

import os
import shutil
import logging
from contextlib import nullcontext
from queue import Empty

import torch
import soundfile as sf

from rvc.triton_client import TritonSparkClient
from rvc.rvc_init import get_vc

logger = logging.getLogger(__name__)


def persistent_tts_worker(
    worker_id: int,
    job_queue,
    active_event,
    server_addr: str,
    server_port: int,
    model_manager,
):
    """
    Persistent TTS worker using Triton inference server.

    This worker connects to Triton via gRPC and processes TTS jobs.
    No CUDA stream needed - Triton handles GPU internally.

    Args:
        worker_id: Unique worker ID
        job_queue: Queue for receiving jobs
        active_event: Event to signal when worker is active/idle
        server_addr: Triton server address (e.g., "localhost")
        server_port: Triton gRPC port (e.g., 8001)
        model_manager: Reference to the model manager
    """
    logger.info(f"TTS Worker {worker_id}: Connecting to Triton at {server_addr}:{server_port}")

    # Initialize Triton client
    tts_client = TritonSparkClient(
        server_addr=server_addr,
        server_port=server_port,
    )

    # Verify connection
    if not tts_client.is_server_ready():
        logger.error(f"TTS Worker {worker_id}: Triton server not ready!")
        return

    logger.info(f"TTS Worker {worker_id}: Connected and ready")

    try:
        while True:
            try:
                # Get job from queue with timeout
                job = job_queue.get(timeout=1.0)

                # Check for shutdown signal
                if job is None:
                    logger.info(f"TTS Worker {worker_id}: Received shutdown signal")
                    break

                # Mark as active
                active_event.set()

                # Unpack job (no cuda_stream for Triton)
                (
                    queue_lock,
                    sentence_queue,
                    sentence_count,
                    processed_count,
                    base_fragment_num,
                    prompt_speech,
                    prompt_text_clean,
                    tts_to_rvc_queue,
                    tts_complete_events,
                    num_rvc_workers,
                ) = job

                # Process sentences from priority queue
                while True:
                    with queue_lock:
                        if sentence_queue.empty():
                            break

                        priority, global_idx, sentence = sentence_queue.get()
                        with processed_count.get_lock():
                            processed_count.value += 1
                            current_count = processed_count.value

                    fragment_num = base_fragment_num + global_idx
                    tts_filename = f"fragment_{fragment_num}.wav"
                    save_path = os.path.join("./TEMP/spark", tts_filename)

                    logger.info(
                        f"TTS Worker {worker_id}: Processing sentence {global_idx + 1}/{sentence_count} "
                        f"(priority {priority}): {sentence[:30]}..."
                    )

                    try:
                        # Call Triton for TTS inference
                        wav = tts_client.inference(
                            text=sentence,
                            prompt_speech=prompt_speech,
                            prompt_text=prompt_text_clean,
                        )

                        # Save output
                        sf.write(save_path, wav, samplerate=16000)
                        logger.info(f"TTS Worker {worker_id}: Audio saved at: {save_path}")

                        # Queue for RVC processing
                        tts_to_rvc_queue.put((global_idx, fragment_num, sentence, save_path))

                    except Exception as e:
                        logger.error(f"TTS Worker {worker_id} error for sentence {global_idx}: {e}")
                        tts_to_rvc_queue.put((global_idx, fragment_num, sentence, None, str(e)))

                logger.info(f"TTS Worker {worker_id}: Completed processing sentences")
                tts_complete_events[worker_id].set()

                # If all TTS workers are done, add sentinel values for RVC workers
                if all(event.is_set() for event in tts_complete_events):
                    for _ in range(num_rvc_workers):
                        tts_to_rvc_queue.put(None)

                # Mark as idle
                model_manager.mark_tts_worker_idle(worker_id)

            except Empty:
                # No job, continue waiting
                continue
            except Exception as e:
                logger.error(f"TTS Worker {worker_id} unexpected error: {e}")
                model_manager.mark_tts_worker_idle(worker_id)

    finally:
        # Clean up
        logger.info(f"TTS Worker {worker_id}: Shutting down")
        tts_client.close()


def persistent_rvc_worker(
    worker_id: int,
    cuda_stream,
    job_queue,
    active_event,
    model_manager,
):
    """
    Persistent RVC worker that processes voice conversion jobs.

    Uses CUDA streams for parallel inference - multiple RVC workers
    can process concurrently without blocking each other.

    Args:
        worker_id: Unique worker ID
        cuda_stream: CUDA stream for this worker's GPU operations
        job_queue: Queue for receiving jobs
        active_event: Event to signal when worker is active/idle
        model_manager: Reference to the model manager
    """
    logger.info(f"RVC Worker {worker_id}: Starting (stream={cuda_stream is not None})")

    try:
        while True:
            try:
                # Get job from queue with timeout
                job = job_queue.get(timeout=1.0)

                # Check for shutdown signal
                if job is None:
                    logger.info(f"RVC Worker {worker_id}: Received shutdown signal")
                    break

                # Mark as active
                active_event.set()

                # Unpack job
                (
                    tts_to_rvc_queue,
                    rvc_results_queue,
                    rvc_complete_events,
                    tts_complete_events,
                    spk_item,
                    vc_transform,
                    f0method,
                    file_index1,
                    file_index2,
                    index_rate,
                    filter_radius,
                    resample_sr,
                    rms_mix_rate,
                    protect,
                    processing_complete,
                ) = job

                # Get VC instance (initialized via rvc_init)
                vc = get_vc()

                # Process items from TTS queue
                while True:
                    try:
                        item = tts_to_rvc_queue.get(timeout=0.5)
                    except Empty:
                        # Check if all TTS workers are done
                        if all(event.is_set() for event in tts_complete_events):
                            break
                        continue

                    # Sentinel value = shutdown
                    if item is None:
                        break

                    # Check for TTS error (5-tuple)
                    if len(item) == 5:
                        i, fragment_num, sentence, _, error = item
                        rvc_results_queue.put(
                            (i, None, None, False, f"TTS error for sentence {i + 1}: {error}")
                        )
                        continue

                    # Normal item (4-tuple)
                    i, fragment_num, sentence, tts_path = item

                    if not tts_path or not os.path.exists(tts_path):
                        rvc_results_queue.put(
                            (i, None, None, False, f"No TTS output for sentence {i + 1}")
                        )
                        continue

                    # Output path
                    rvc_path = os.path.join("./TEMP/rvc", f"fragment_{fragment_num}.wav")

                    try:
                        logger.info(f"RVC Worker {worker_id}: Processing fragment {fragment_num}")

                        # Use CUDA stream for RVC inference
                        stream_ctx = (
                            torch.cuda.stream(cuda_stream)
                            if cuda_stream and torch.cuda.is_available()
                            else nullcontext()
                        )

                        with stream_ctx:
                            f0_file = None
                            output_info, output_audio = vc.vc_single(
                                spk_item,
                                tts_path,
                                vc_transform,
                                f0_file,
                                f0method,
                                file_index1,
                                file_index2,
                                index_rate,
                                filter_radius,
                                resample_sr,
                                rms_mix_rate,
                                protect,
                            )

                        # Save RVC output
                        rvc_saved = False
                        try:
                            if isinstance(output_audio, str) and os.path.exists(output_audio):
                                shutil.copy2(output_audio, rvc_path)
                                rvc_saved = True
                            elif isinstance(output_audio, tuple) and len(output_audio) >= 2:
                                sf.write(rvc_path, output_audio[1], output_audio[0])
                                rvc_saved = True
                            elif hasattr(output_audio, "name") and os.path.exists(output_audio.name):
                                shutil.copy2(output_audio.name, rvc_path)
                                rvc_saved = True
                        except Exception as e:
                            output_info += f"\nError saving RVC output: {e}"

                        logger.info(f"RVC Worker {worker_id}: Inference completed for {tts_path}")

                        # Build info message
                        info_message = (
                            f"Sentence {i + 1}: {sentence[:30]}{'...' if len(sentence) > 30 else ''}\n"
                        )
                        info_message += f"  - Spark output: {tts_path}\n"
                        if rvc_saved:
                            info_message += f"  - RVC output (Worker {worker_id}): {rvc_path}"
                        else:
                            info_message += f"  - Could not save RVC output to {rvc_path}"

                        rvc_results_queue.put(
                            (i, tts_path, rvc_path if rvc_saved else None, rvc_saved, info_message)
                        )

                    except Exception as e:
                        logger.error(f"RVC Worker {worker_id} error for sentence {i}: {e}")
                        info_message = (
                            f"Sentence {i + 1}: {sentence[:30]}{'...' if len(sentence) > 30 else ''}\n"
                        )
                        info_message += f"  - Spark output: {tts_path}\n"
                        info_message += f"  - RVC processing error (Worker {worker_id}): {e}"
                        rvc_results_queue.put((i, tts_path, None, False, info_message))

                logger.info(f"RVC Worker {worker_id}: Completed current job")
                rvc_complete_events[worker_id].set()

                # Signal processing complete if all RVC workers done
                if all(event.is_set() for event in rvc_complete_events):
                    processing_complete.set()

                # Mark as idle
                model_manager.mark_rvc_worker_idle(worker_id)

            except Empty:
                continue
            except Exception as e:
                logger.error(f"RVC Worker {worker_id} unexpected error: {e}")
                model_manager.mark_rvc_worker_idle(worker_id)

    finally:
        logger.info(f"RVC Worker {worker_id}: Shutting down")
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
