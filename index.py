from flask import Flask
from flask_socketio import SocketIO, emit
import requests
import openai
import io
from langdetect import detect, DetectorFactory

app = Flask(__name__)
socketio = SocketIO(app, async_mode="gevent", cors_allowed_origins="*")



# Set your API keys here

# Ensure reproducible results for langdetect
DetectorFactory.seed = 0

# Global in-memory buffer to collect audio chunks.
# In production, use session-based or client-specific buffers.
audio_buffer = io.BytesIO()

def speech_to_text(audio_file_obj):
    """
    Converts an audio file-like object to text using the Sarvam.ai Speech-to-Text API.
    """
    url = "https://api.sarvam.ai/speech-to-text"
    # Rewind the buffer to ensure we read from the beginning.
    audio_file_obj.seek(0)
    files = {
        "audio_file": ("streamed_audio.wav", audio_file_obj, "audio/wav")
    }
    data = {
        "model": "saarika:v2",
        "language_code": "unknown",
        "with_timestamps": "false",
        "with_diarization": "false",
        "num_speakers": "123"
    }
    response = requests.post(url, files=files, data=data)
    try:
        result = response.json()
        transcript = result.get('transcript', '')
    except Exception as e:
        transcript = ""
    return transcript

def get_chatgpt_response(transcript):
    """
    Uses the ChatGPT API to generate an answer based on the transcript.
    The system prompt instructs the model to act as a loan agent and answer in the language of the input.
    """
    system_prompt = (
        "You are a loan agent. Explain the loan eligibility criteria, "
        "restrictions, and who can or cannot apply. Always answer in the language of the user's input."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": transcript}
    ]
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=messages
    )
    answer_text = response.choices[0].message.content.strip()
    return answer_text

def detect_language(transcript):
    """
    Detects the language of the given transcript using langdetect.
    Maps the detected two-letter language code to a locale code suitable for Sarvam.ai TTS.
    """
    try:
        lang_code = detect(transcript)
    except Exception as e:
        lang_code = "hi"
    lang_map = {
        "bn": "bn-IN",
        "gu": "gu-IN",
        "hi": "hi-IN",
        "kn": "kn-IN",
        "ml": "ml-IN",
        "mr": "mr-IN",
        "or": "od-IN",  # sometimes 'or' is returned for Oriya
        "pa": "pa-IN",
        "ta": "ta-IN",
        "te": "te-IN",
        "en": "en-US"   # fallback for English
    }
    return lang_map.get(lang_code, "hi-IN")

def text_to_speech(text, language_code="hi-IN"):
    """
    Converts the given text to speech using the Sarvam.ai Text-to-Speech API.
    """
    url = "https://api.sarvam.ai/text-to-speech"
    payload = {
        "inputs": [text],
        "target_language_code": language_code,
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
    Receives binary audio chunks from the client via websocket and appends them to the global buffer.
    """
    global audio_buffer
    # 'data' is expected to be binary audio data.
    audio_buffer.write(data)
    # Optionally, confirm receipt of the chunk to the client.
    emit('chunk_received', {'status': 'received'})

@socketio.on('audio_stream_end')
def handle_audio_stream_end(data):
    """
    Called when the client signals that the audio streaming is complete.
    Processes the buffered audio, generates a response, converts it to speech, and sends it back.
    
    Expected 'data' may include a 'language' field (e.g., "hi-IN", "te-IN") from a dropdown.
    """
    global audio_buffer
    # Process the complete audio buffer.
    transcript = speech_to_text(audio_buffer)
    if not transcript:
        emit('error', {'message': 'Could not transcribe audio'})
        # Reset the buffer.
        audio_buffer.seek(0)
        audio_buffer.truncate(0)
        return
    
    # Generate a response using ChatGPT.
    answer_text = get_chatgpt_response(transcript)
    
    # Determine target language:
    # If the client provided a language code, use it if valid; otherwise, auto-detect.
    allowed_languages = {"bn-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "od-IN", "pa-IN", "ta-IN", "te-IN"}
    language_code = data.get('language')
    if language_code not in allowed_languages:
        language_code = detect_language(transcript)
    
    # Convert the response text to speech.
    audio_response = text_to_speech(answer_text, language_code)
    
    # Send the audio response back to the client.
    emit('audio_response', audio_response, binary=True)
    
    # Reset the buffer for the next audio stream.
    audio_buffer.seek(0)
    audio_buffer.truncate(0)

if __name__ == '__main__':
    socketio.run(app, debug=True)
from flask import Flask
from flask_socketio import SocketIO, emit
import requests
import openai
import io
from langdetect import detect, DetectorFactory

app = Flask(__name__)
socketio = SocketIO(app)

# Set your API keys here

# Ensure reproducible results for langdetect
DetectorFactory.seed = 0

# Global in-memory buffer to collect audio chunks.
# In production, use session-based or client-specific buffers.
audio_buffer = io.BytesIO()

def speech_to_text(audio_file_obj):
    """
    Converts an audio file-like object to text using the Sarvam.ai Speech-to-Text API.
    """
    url = "https://api.sarvam.ai/speech-to-text"
    # Rewind the buffer to ensure we read from the beginning.
    audio_file_obj.seek(0)
    files = {
        "audio_file": ("streamed_audio.wav", audio_file_obj, "audio/wav")
    }
    data = {
        "model": "saarika:v2",
        "language_code": "unknown",
        "with_timestamps": "false",
        "with_diarization": "false",
        "num_speakers": "123"
    }
    response = requests.post(url, files=files, data=data)
    try:
        result = response.json()
        transcript = result.get('transcript', '')
    except Exception as e:
        transcript = ""
    return transcript

def get_chatgpt_response(transcript):
    """
    Uses the ChatGPT API to generate an answer based on the transcript.
    The system prompt instructs the model to act as a loan agent and answer in the language of the input.
    """
    system_prompt = (
        "You are a loan agent. Explain the loan eligibility criteria, "
        "restrictions, and who can or cannot apply. Always answer in the language of the user's input."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": transcript}
    ]
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=messages
    )
    answer_text = response.choices[0].message.content.strip()
    return answer_text

def detect_language(transcript):
    """
    Detects the language of the given transcript using langdetect.
    Maps the detected two-letter language code to a locale code suitable for Sarvam.ai TTS.
    """
    try:
        lang_code = detect(transcript)
    except Exception as e:
        lang_code = "hi"
    lang_map = {
        "bn": "bn-IN",
        "gu": "gu-IN",
        "hi": "hi-IN",
        "kn": "kn-IN",
        "ml": "ml-IN",
        "mr": "mr-IN",
        "or": "od-IN",  # sometimes 'or' is returned for Oriya
        "pa": "pa-IN",
        "ta": "ta-IN",
        "te": "te-IN",
        "en": "en-US"   # fallback for English
    }
    return lang_map.get(lang_code, "hi-IN")

def text_to_speech(text, language_code="hi-IN"):
    """
    Converts the given text to speech using the Sarvam.ai Text-to-Speech API.
    """
    url = "https://api.sarvam.ai/text-to-speech"
    payload = {
        "inputs": [text],
        "target_language_code": language_code,
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
    global audio_buffer
    audio_buffer.write(data)
    print("Received an audio chunk.")
    emit('chunk_received', {'status': 'received'})


@socketio.on('audio_stream_end')
def handle_audio_stream_end(data):
    """
    Called when the client signals that the audio streaming is complete.
    Processes the buffered audio, generates a response, converts it to speech, and sends it back.
    
    Expected 'data' may include a 'language' field (e.g., "hi-IN", "te-IN") from a dropdown.
    """
    global audio_buffer
    # Process the complete audio buffer.
    transcript = speech_to_text(audio_buffer)
    if not transcript:
        emit('error', {'message': 'Could not transcribe audio'})
        # Reset the buffer.
        audio_buffer.seek(0)
        audio_buffer.truncate(0)
        return
    
    # Generate a response using ChatGPT.
    answer_text = get_chatgpt_response(transcript)
    
    # Determine target language:
    # If the client provided a language code, use it if valid; otherwise, auto-detect.
    allowed_languages = {"bn-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "od-IN", "pa-IN", "ta-IN", "te-IN"}
    language_code = data.get('language')
    if language_code not in allowed_languages:
        language_code = detect_language(transcript)
    
    # Convert the response text to speech.
    audio_response = text_to_speech(answer_text, language_code)
    
    # Send the audio response back to the client.
    emit('audio_response', audio_response, binary=True)
    
    # Reset the buffer for the next audio stream.
    audio_buffer.seek(0)
    audio_buffer.truncate(0)

if __name__ == '__main__':
    socketio.run(app, debug=True)
