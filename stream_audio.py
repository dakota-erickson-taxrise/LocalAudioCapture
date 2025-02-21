# client
import asyncio
import base64
import json
import wave
import sounddevice as sd
import numpy as np
import websockets
import platform
from queue import Queue
from threading import Thread

class AudioStreamer:
    def __init__(self, websocket_url, sample_rate=16000, chunk_duration_ms=500):
        self.websocket_url = websocket_url
        self.sample_rate = sample_rate
        self.chunk_duration_ms = chunk_duration_ms
        self.chunk_size = int(sample_rate * (chunk_duration_ms / 1000))
        self.audio_format = 'int16'
        self.audio_queue = Queue()
        self.is_running = True
        
        # Platform-specific setup
        self.system = platform.system()
        if self.system not in ['Darwin', 'Windows']:
            raise RuntimeError(f"Unsupported operating system: {self.system}")

    def _convert_to_wav(self, audio_chunk):
        """Convert raw audio data to WAV format with PCM16 encoding"""
        with wave.open('temp.wav', 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(audio_chunk.tobytes())
            
        with open('temp.wav', 'rb') as wav_file:
            return base64.b64encode(wav_file.read()).decode('utf-8')

    def audio_callback(self, indata, frames, time, status):
        # The unused parameters are necessary because of the sound device definition
        if status:
            print(f'Audio callback status: {status}')
            return
                
        raw_bytes = indata.tobytes()
        base64_data = base64.b64encode(raw_bytes).decode('utf-8')
        
        print(f"Input data type: {indata.dtype}")
        print(f"Input data shape: {indata.shape}")
        print(f"Max amplitude: {np.max(np.abs(indata))}")
        
        self.audio_queue.put(base64_data)


    async def websocket_sender(self):
        """Async task to send audio data via WebSocket"""
        while self.is_running:
            try:
                async with websockets.connect(self.websocket_url) as websocket:
                    while self.is_running:
                        if not self.audio_queue.empty():
                            audio_data = self.audio_queue.get()
                            message = json.dumps({"audio_data": audio_data})
                            await websocket.send(message)
                        else:
                            await asyncio.sleep(0.01)
            except Exception as e:
                print(f"WebSocket error: {e}")
                await asyncio.sleep(1)

    def start_audio_capture(self):
        """Start the audio capture in a separate thread"""
        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype=self.audio_format,
            blocksize=self.chunk_size,
            callback=self.audio_callback
        ):
            while self.is_running:
                sd.sleep(100)

    async def start_streaming(self):
        """Start both audio capture and WebSocket streaming"""
        print(f"Started audio streaming to {self.websocket_url}")
        print("Press Ctrl+C to stop")
        
        # Start audio capture in a separate thread
        audio_thread = Thread(target=self.start_audio_capture)
        audio_thread.start()
        
        # Start WebSocket sender
        try:
            await self.websocket_sender()
        except KeyboardInterrupt:
            print("\nStopping audio capture...")
        finally:
            self.is_running = False
            audio_thread.join()

def main():
    websocket_url = "wss://cloudtarget.fly.dev"
    streamer = AudioStreamer(websocket_url)
    
    try:
        asyncio.run(streamer.start_streaming())
    except KeyboardInterrupt:
        print("\nProgram terminated by user")
    except Exception as e:
        print(f"Program error: {e}")

if __name__ == "__main__":
    main()
