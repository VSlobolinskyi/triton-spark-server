"""Test scripts for voice synthesis pipeline.

Run tests from Colab or command line:
    python -m tests.test_http_api --host localhost --port 8080
    python -m tests.test_connection --host localhost --port 8001
    python -m tests.test_tts --host localhost --port 8001 --reference ref.wav
    python -m tests.test_rvc --host localhost --port 8080 --input audio.wav
    python -m tests.test_pipeline --host localhost --port 8080 --reference ref.wav
"""
