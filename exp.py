from flask import Flask
from flask_socketio import SocketIO, emit
import requests
import io
import os
import time
from groq import Groq  # Ensure you have installed the groq package

app = Flask(__name__)
socketio = SocketIO(app, async_mode="gevent", cors_allowed_origins="*")


# Set your API keys here
GROQ_API_KEY = 'api'  # Replace with your actual Groq API key
SARVAM_SUBSCRIPTION_KEY = 'api'

# Create a Groq client instance using the provided API key.
groq_client = Groq(api_key=GROQ_API_KEY)

# Global in-memory buffer to collect audio chunks.
audio_buffer = io.BytesIO()
is_processing = False  # Global flag to avoid overlapping processing

def reset_audio_buffer():
    global audio_buffer
    audio_buffer.seek(0)
    audio_buffer.truncate(0)

def wait_for_silence():
    # In a real-world scenario, implement proper silence detection.
    # Here, we simply sleep for 2 seconds to simulate waiting for the user to pause.
    time.sleep(2)

def speech_to_text(audio_file_obj):
    """
    Sends the audio file-like object to Sarvam.ai's Speech-to-Text API
    and returns the transcript text and language_code.
    """
    url = "https://api.sarvam.ai/speech-to-text"
    headers = {"api-subscription-key": SARVAM_SUBSCRIPTION_KEY}
    audio_file_obj.seek(0)
    files = {"file": ("streamed_audio.wav", audio_file_obj, "audio/wav")}
    data = {
        "model": "saarika:v2",
        "language_code": "unknown",
        "with_timestamps": "false",
        "with_diarization": "false",
        "num_speakers": "123"
    }
    response = requests.post(url, files=files, data=data, headers=headers)
    print("Sarvam.ai API status code:", response.status_code)
    print("Sarvam.ai API response text:", response.text)
    try:
        result = response.json()
        transcript = result.get('transcript', '')
        language_code = result.get('language_code', 'hi-IN')
    except Exception as e:
        print("Error parsing JSON:", e)
        transcript = ""
        language_code = "hi-IN"
    return transcript, language_code

def get_groq_response(transcript):
    """
    Uses the Groq Python client to generate an answer based on the transcript.
    Constructs the conversation messages and returns the response text.
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You are a loan agent. Explain the loan eligibility criteria, restrictions, and who can or cannot apply. "
                "Always answer in the language of the user's input. Please keep your response under 500 characters."
            )
        },
        {"role": "user", "content": transcript}
    ]
    
    print("Starting Groq API call with transcript:", transcript)
    try:
        chat_completion = groq_client.chat.completions.create(
            messages=messages,
            model="llama-3.3-70b-versatile",  # Adjust the model as required.
            stream=False,
        )
        answer_text = chat_completion.choices[0].message.content.strip()
        print("Groq API call successful. Answer:", answer_text)
    except Exception as e:
        print("Error calling Groq API:", e)
        answer_text = ""
    return answer_text

def text_to_speech(text, language_code="en-IN"):
    """
    Converts the given text to speech using the Sarvam.ai Text-to-Speech API.
    Overrides the language to English ("en-IN") to ensure audio is in English.
    """
    url = "https://api.sarvam.ai/text-to-speech"
    payload = {
        "inputs": [text],
        "target_language_code": language_code,  # Force English audio.
        "speaker": "meera",
        "pitch": 0,
        "pace": 1.65,
        "loudness": 1.5,
        "speech_sample_rate": 8000,
        "enable_preprocessing": False,
        "model": "bulbul:v1",
        "eng_interpolation_wt": 123,
        "override_triplets": {}
    }
    headers = {
        "api-subscription-key": SARVAM_SUBSCRIPTION_KEY,
        "Content-Type": "application/json"
    }
    response = requests.post(url, json=payload, headers=headers)
    return response.content

@socketio.on('audio_chunk')
def handle_audio_chunk(data):
    """
    Receives binary audio chunks from the client and appends them to the buffer.
    """
    global audio_buffer
    audio_buffer.write(data)
    print("Received an audio chunk.")
    emit('chunk_received', {'status': 'received'})

@socketio.on('audio_stream_end')
def handle_audio_stream_end(data):
    """
    Called when the client signals that audio streaming is complete.
    Processes the buffered audio:
      1. Transcribes the audio using Sarvam.ai.
      2. Uses the transcript to get a response from the Groq API.
      3. Converts the Groq response to speech.
      4. Sends the final audio back to the client.
    """
    global audio_buffer, is_processing
    if is_processing:
        print("TTS processing already in progress. Ignoring new request.")
        reset_audio_buffer()
        return

    wait_for_silence()
    transcript, language_code = speech_to_text(audio_buffer)
    if not transcript:
        emit('error', {'message': 'Could not transcribe audio'})
        reset_audio_buffer()
        return

    is_processing = True
    answer_text = get_groq_response(transcript)
    # Override language to English regardless of transcription result.
    tts_audio = text_to_speech(answer_text, language_code="en-IN")
    emit('audio_response', tts_audio, binary=True)
    reset_audio_buffer()
    is_processing = False

if __name__ == '__main__':
    socketio.run(app, debug=True)
