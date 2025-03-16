from flask import Flask
from flask_socketio import SocketIO, emit
import requests
import io
import os
import time
from groq import Groq  # Ensure you have installed the groq package
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
socketio = SocketIO(app, async_mode="gevent", cors_allowed_origins="*")

# Set your API keys here (or use environment variables)
GROQ_API_KEY = os.getenv('GROQ_API_KEY', 'your_groq_api_key_here')
SARVAM_SUBSCRIPTION_KEY = os.getenv('SARVAM_SUBSCRIPTION_KEY', 'your_sarvam_subscription_key_here')
groq_client = Groq(api_key=GROQ_API_KEY)
# Global in-memory buffer to collect audio chunks.
audio_buffer = io.BytesIO()
is_processing = False  # Global flag to avoid overlapping processing
client_name = None
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
    Sends the audio file-like object to Sarvam.ai's Speech-to-Text-Translate API.
    Returns the transcript and the detected language code.
    """
    url = "https://api.sarvam.ai/speech-to-text-translate"
    headers = {
        "api-subscription-key": SARVAM_SUBSCRIPTION_KEY
    }
# Create a Groq client instance using the provided API key.
    #groq_client = Groq(api_key=GROQ_API_KEY)

    # Ensure the file pointer is at the beginning
    audio_file_obj.seek(0)
    files = {
        "file": ("streamed_audio.wav", audio_file_obj, "audio/wav")
    }
    data = {
        "prompt": "<string>",  # Adjust prompt if needed
        "model": "saaras:v2",
        "with_diarization": "false",
        "num_speakers": "1"
    }
    response = requests.post(url, files=files, data=data, headers=headers)
    print("Sarvam.ai Speech-to-Text-Translate API status code:", response.status_code)
    print("Response text:", response.text)
    try:
        result = response.json()
        transcript = result.get('transcript', '')
        language_code = result.get('language_code', 'en-IN')
    except Exception as e:
        print("Error parsing JSON:", e)
        transcript = ""
        language_code = "en-IN"
    return transcript, language_code

def transliterate_text(text, source_lang, target_lang='en-IN'):
    """
    Transliterates text from a native script (e.g., Devanagari) to Roman (English) script.
    """
    url = "https://api.sarvam.ai/transliterate"
    payload = {
        "input": text,
        "source_language_code": source_lang,
        "target_language_code": target_lang,
        "numerals_format": "international",
        "spoken_form_numerals_language": "native",
        "spoken_form": False
    }
    headers = {
        "Content-Type": "application/json",
        "api-subscription-key": SARVAM_SUBSCRIPTION_KEY
    }
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 200:
        result = response.json()
        transliterated_text = result.get('transliterated_text', '')
        return transliterated_text
    else:
        print(f"Transliterate API error: {response.status_code}")
        return text

def get_groq_response(transcript):
    """
    Uses the Groq API to generate an answer based on the transcript.
    The system prompt adapts based on whether the client's name is known.
    """
    system_message = ("""
        "You are a professional loan officer. "
        "Engage in a friendly dialogue to understand their financial goals, aspirations, and any concerns they might have. "
        "Provide tailored advice on loan options, eligibility criteria, and potential restrictions based on their unique situation. "
        "Ensure the conversation is empathetic, informative, and concise, keeping responses under 500 characters."

        """
        )
    
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": transcript}
    ]
    
    print("Starting Groq API call with transcript:", transcript)
    try:
        chat_completion = groq_client.chat.completions.create(
            messages=messages,
            model="gemma2-9b-it",  # Adjust as needed
            stream=False,
        )
        answer_text = chat_completion.choices[0].message.content.strip()
        print("Groq API call successful. Answer:", answer_text)
        
        # Optional: If the agent provides the client's name in its answer,
        # you can add logic here to parse and save it.
        # For example, if answer_text contains "Your name is John", extract "John".
        # (Implementation of parsing logic is up to you.)
        
    except Exception as e:
        print("Error calling Groq API:", e)
        answer_text = ""
    return answer_text
def text_to_speech(text, language_code="en-IN"):
    """
    Converts the given text to speech using the Sarvam.ai Text-to-Speech API.
    """
    url = "https://api.sarvam.ai/text-to-speech"
    payload = {
        "inputs": [text],
        "target_language_code": language_code,  # Force English audio.
        "speaker": "meera",
        "pitch": 0,
        "pace": 1.3,
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
      1. Transcribes the audio using Sarvam.ai's Speech-to-Text-Translate API.
      2. If the transcript is not in English, transliterates it to English.
      3. Uses the (possibly transliterated) transcript to get a tailored response from the Groq API.
      4. Converts the response to speech using Sarvam.ai's Text-to-Speech API.
      5. Sends the final audio back to the client.
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

    # If the input is not in English, transliterate it to a Romanized (English) version.
    if language_code != 'en-IN':
        transcript = transliterate_text(transcript, source_lang=language_code, target_lang="en-IN")
        print("Transliterated transcript:", transcript)

    is_processing = True
    answer_text = get_groq_response(transcript)
    # We force the final TTS output to be in English.
    tts_audio = text_to_speech(answer_text, language_code="en-IN")
    emit('audio_response', tts_audio, binary=True)
    reset_audio_buffer()
    is_processing = False

if __name__ == '__main__':
    socketio.run(app, debug=True)
