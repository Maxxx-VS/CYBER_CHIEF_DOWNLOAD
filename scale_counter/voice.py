import os
import json
import threading
import time
import subprocess
import pyaudio
import ctypes
import numpy as np
from vosk import Model, KaldiRecognizer, SetLogLevel


TARGET_USB_KEYWORDS = (
    "AB13X",
    "Generic_AB13X",
    "USB Audio",
)


class VoiceService:
    def __init__(self, config, speaking_event, tts):
        self.config = config
        self.speaking_event = speaking_event
        self.tts = tts
        self.running = True

        self.target_word = self.config.KEY_WORD.lower()
        self.mic_gain = getattr(self.config, 'MIC_GAIN', 1.0)

        self._setup_logging_suppression()
        self._ensure_mic_level()

        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    # --------------------------------------------------
    # ALSA helpers
    # --------------------------------------------------

    def _ensure_mic_level(self):
        try:
            subprocess.run(
                ['amixer', '-c', 'Audio', 'sset', 'Mic', '100%', 'unmute'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            subprocess.run(
                ['amixer', '-c', 'Audio', 'sset', 'Auto Gain Control', 'on'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            print(f"[Voice] amixer error: {e}")

    def _setup_logging_suppression(self):
        SetLogLevel(-1)
        try:
            ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(
                None, ctypes.c_char_p, ctypes.c_int,
                ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p
            )

            def py_error_handler(filename, line, function, err, fmt):
                pass

            self.c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)
            asound = ctypes.cdll.LoadLibrary('libasound.so.2')
            asound.snd_lib_error_set_handler(self.c_error_handler)
        except Exception:
            pass

    # --------------------------------------------------
    # PyAudio helpers
    # --------------------------------------------------

    def _get_input_device_index(self, p):
        for i in range(p.get_device_count()):
            try:
                info = p.get_device_info_by_index(i)
                name = info.get("name", "")
                if (
                    info.get("maxInputChannels", 0) > 0
                    and any(k in name for k in TARGET_USB_KEYWORDS)
                ):
                    print(f"✓ [Voice] Mic: {name}")
                    return i
            except Exception:
                continue

        info = p.get_default_input_device_info()
        print(f"! [Voice] fallback mic: {info['name']}")
        return info['index']

    # --------------------------------------------------
    # Audio helpers
    # --------------------------------------------------

    def _calculate_rms(self, data):
        audio = np.frombuffer(data, dtype=np.int16)
        if audio.size == 0:
            return 0
        return np.sqrt(np.mean(audio.astype(np.float64) ** 2))

    def _play_vosk_sound(self):
        path = self.config.SOUND_PATH_VOSK
        if not os.path.exists(path):
            return
        try:
            self.speaking_event.set()
            subprocess.run(
                ['mpg123', '-q', path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        finally:
            self.speaking_event.clear()

    # --------------------------------------------------
    # Main worker
    # --------------------------------------------------

    def _worker(self):
        if not os.path.exists(self.config.VOSK_MODEL_PATH):
            print(f"[Voice] Model not found: {self.config.VOSK_MODEL_PATH}")
            return

        print(f"--- Voice active (KEY: '{self.target_word}') ---")

        model = Model(self.config.VOSK_MODEL_PATH)

        STREAM_LIFETIME = 300            # 5 минут
        RECOGNIZER_LIFETIME = 120        # 2 минуты
        MAX_SILENCE_TIME = 10.0
        MAX_NO_RECOGNITION_TIME = 30.0   # watchdog

        while self.running:
            p = stream = recognizer = None

            try:
                p = pyaudio.PyAudio()
                device_index = self._get_input_device_index(p)

                stream = p.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=48000,
                    input=True,
                    frames_per_buffer=4000,
                    input_device_index=device_index
                )
                stream.start_stream()

                def create_recognizer():
                    r = KaldiRecognizer(model, 48000)
                    r.SetWords(True)
                    return r

                recognizer = create_recognizer()
                recognizer_start_time = time.time()
                last_recognition_time = time.time()

                start_time = time.time()
                last_sound_time = time.time()

                while self.running:
                    now = time.time()

                    # --- НЕ слушаем микрофон, пока говорим ---
                    if self.speaking_event.is_set():
                        time.sleep(0.05)
                        continue

                    if now - start_time > STREAM_LIFETIME:
                        print("[Voice] Stream lifetime reached")
                        break

                    data = stream.read(4000, exception_on_overflow=False)

                    # --- защита от пустого аудио ---
                    if np.max(np.abs(np.frombuffer(data, dtype=np.int16))) < 5:
                        continue

                    rms = self._calculate_rms(data)
                    if rms > 10:
                        last_sound_time = now

                    if now - last_sound_time > MAX_SILENCE_TIME:
                        print("[Voice] Silence timeout")
                        break

                    if self.mic_gain > 1.0:
                        audio = np.frombuffer(data, dtype=np.int16)
                        audio = np.clip(audio * self.mic_gain, -32768, 32767)
                        data = audio.astype(np.int16).tobytes()

                    # --- Watchdog ---
                    if (
                        now - recognizer_start_time > RECOGNIZER_LIFETIME
                        or now - last_recognition_time > MAX_NO_RECOGNITION_TIME
                    ):
                        print("[Voice] Full audio reset (watchdog)")
                        break

                    if recognizer.AcceptWaveform(data):
                        last_recognition_time = now
                        res = json.loads(recognizer.Result())
                        text = res.get("text", "").lower()

                        if self.target_word in text:
                            print(f"[KEY WORD] {self.target_word.upper()}")
                            self._play_vosk_sound()
                            self.tts.queue.put(
                                f"Распознано слово: {self.target_word}"
                            )
                    else:
                        # --- PartialResult тоже считается активностью ---
                        try:
                            partial = json.loads(recognizer.PartialResult())
                            if partial.get("partial"):
                                last_recognition_time = now
                        except Exception:
                            pass

            except Exception as e:
                print(f"[Voice] Error: {e}")
                time.sleep(1)

            finally:
                try:
                    if recognizer:
                        recognizer.FinalResult()
                except Exception:
                    pass

                try:
                    if stream:
                        stream.stop_stream()
                        stream.close()
                except Exception:
                    pass

                try:
                    if p:
                        p.terminate()
                except Exception:
                    pass

                time.sleep(0.5)

    # --------------------------------------------------

    def stop(self):
        self.running = False
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)
