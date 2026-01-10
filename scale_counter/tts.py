# tts.py
import subprocess
import threading
import queue
import os
import time

class PiperTTS:
    def __init__(self, config, speaking_event):
        """
        :param speaking_event: threading.Event для синхронизации с микрофоном
        """
        self.config = config
        self.speaking_event = speaking_event
        self.queue = queue.Queue()
        self.running = True
        
        # Настройка громкости при старте
        self._set_system_volume()
        
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()
        self.last_weight_grams = 0 

    def _set_system_volume(self):
        """Устанавливает системную громкость (ALSA) согласно конфигу"""
        try:
            vol = self.config.VOLUME_LEVEL.replace('%', '')
            subprocess.run(
                ['amixer', 'sset', 'PCM', f'{vol}%'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            subprocess.run(
                ['amixer', 'sset', 'Master', f'{vol}%'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            pass # Игнорируем ошибки установки громкости для чистоты вывода

    def play_change_notification(self, is_increase: bool):
        threading.Thread(
            target=self._play_sound_worker, 
            args=(is_increase,), 
            daemon=True
        ).start()

    def play_camera_notification(self):
        """
        Воспроизводит звук ошибки камеры (camera.mp3).
        """
        # print(f"[TTS] Запрос на воспроизведение ошибки камеры: {self.config.SOUND_PATH_CAMERA}")
        threading.Thread(
            target=self._play_file_worker, 
            args=(self.config.SOUND_PATH_CAMERA,), 
            daemon=True
        ).start()

    def _play_file_worker(self, file_path):
        """Универсальный воркер для воспроизведения файла с жестким ожиданием и отладкой"""
        if not os.path.exists(file_path):
            # Оставим только критическую ошибку, если файла нет
            print(f"[TTS] ОШИБКА: Файл звука не найден: {file_path}")
            return

        # 1. Ждем, пока система говорит (aplay занял карту)
        timeout = 6.0
        start_wait = time.time()
        
        while self.speaking_event.is_set():
            if time.time() - start_wait > timeout:
                # print("[TTS] Timeout ожидания очереди звука")
                break
            time.sleep(0.1)

        # 2. Даем ALSA время полностью освободиться
        time.sleep(0.5)

        # 3. Блокируем микрофон и воспроизводим
        self.speaking_event.set()
        try:
            cmd = ['mpg123', '-o', 'alsa', '-q', '-f', '32768', file_path]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )
            
            # Выводим stderr только если код возврата не 0 (ошибка)
            if result.returncode != 0:
                print(f"[TTS] ОШИБКА mpg123: {result.stderr}")
                    
        except Exception as e:
            print(f"[TTS] Критическая ошибка запуска плеера: {e}")
        finally:
            # Разблокируем
            self.speaking_event.clear()

    def _play_sound_worker(self, is_increase):
        sound_path = self.config.SOUND_PATH_PLUS if is_increase else self.config.SOUND_PATH_MINUS
        self._play_file_worker(sound_path)

    def say_text(self, text):
        if text and text.strip():
            self.queue.put(text.strip())

    def _worker(self):
        while self.running:
            try:
                item = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if item is None:
                continue

            last = item
            while True:
                try:
                    nxt = self.queue.get_nowait()
                    if nxt is None: continue
                    last = nxt
                    self.queue.task_done()
                except queue.Empty:
                    break

            try:
                self.speaking_event.set()
                self._speak(last)
            except Exception:
                pass
            finally:
                self.speaking_event.clear()
            
            self.queue.task_done()

    def _speak(self, text):
        json_path = self.config.PIPER_MODEL_PATH.replace('.onnx', '.json')

        if not os.path.exists(self.config.PIPER_BINARY_PATH):
            return

        send_text = text
        if not send_text.endswith(('.', '!', '?')):
            send_text = send_text + '.'
        if not send_text.endswith('\n'):
            send_text = send_text + '\n'

        try:
            piper_cmd = [
                self.config.PIPER_BINARY_PATH,
                '--model', self.config.PIPER_MODEL_PATH,
                '--config', json_path,
                '--length_scale', '0.5',
                '--output_file', '-'
            ]
            aplay_cmd = ['aplay', '-D', 'default', '-q', '-r', '22050', '-f', 'S16_LE', '-t', 'raw', '-']
            
            with open('/dev/null', 'wb') as devnull:
                piper_proc = subprocess.Popen(
                    piper_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=devnull, close_fds=True
                )
                aplay_proc = subprocess.Popen(
                    aplay_cmd, stdin=piper_proc.stdout, stdout=devnull, stderr=devnull
                )

                try:
                    piper_proc.stdin.write(send_text.encode('utf-8'))
                    piper_proc.stdin.flush()
                    piper_proc.stdin.close()
                except Exception:
                    pass

                piper_proc.wait()
                aplay_proc.wait()

        except Exception:
            pass

    def _int_to_words_ru(self, num: int) -> str:
        if num == 0: return "ноль"
        ones = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять", "десять",
                "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать",
                "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
        tens = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
        hundreds = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот"]

        def three_digits_to_words(n: int, gender: str = 'm') -> list:
            parts = []
            h = n // 100
            t = (n % 100) // 10
            o = n % 10
            if h: parts.append(hundreds[h])
            if t == 1: parts.append(ones[10 + o])
            else:
                if t: parts.append(tens[t])
                if o:
                    if o == 1: parts.append("одна" if gender == 'f' else "один")
                    elif o == 2: parts.append("две" if gender == 'f' else "два")
                    else: parts.append(ones[o])
            return parts

        groups = [(("", "", ""), 'm'), (("тысяча", "тысячи", "тысяч"), 'f'), 
                  (("миллион", "миллиона", "миллионов"), 'm'), (("миллиард", "миллиарда", "миллиардов"), 'm')]
        parts = []
        n = num
        group_index = 0
        while n > 0:
            chunk = n % 1000
            n //= 1000
            if chunk:
                gender = groups[group_index][1] if group_index < len(groups) else 'm'
                chunk_words = three_digits_to_words(chunk, gender=('f' if gender == 'f' else 'm'))
                if group_index > 0:
                    forms = groups[group_index][0]
                    last_two = chunk % 100
                    last = chunk % 10
                    if 11 <= last_two <= 14: form = forms[2]
                    else:
                        if last == 1: form = forms[0]
                        elif 2 <= last <= 4: form = forms[1]
                        else: form = forms[2]
                    chunk_words.append(form)
                parts.insert(0, " ".join(chunk_words))
            group_index += 1
        return " ".join(parts).strip()

    def say_weight(self, weight_kg):
        current_grams = 0
        try:
            if isinstance(weight_kg, (float, int)):
                current_grams = int(round(float(weight_kg) * 1000.0))
            else:
                val = float(str(weight_kg).replace(',', '.'))
                current_grams = int(round(val * 1000.0))
            
            current_grams = max(0, current_grams)
            delta_grams = abs(current_grams - self.last_weight_grams)
            
            if delta_grams == 0:
                self.last_weight_grams = current_grams
                return 

            words = self._int_to_words_ru(delta_grams)
            text = words

            self.last_weight_grams = current_grams
            if not text.endswith(('.', '!', '?')):
                text = text + '.'
            self.queue.put(text)
            
        except Exception:
            try:
                if isinstance(weight_kg, float):
                    text = f"{weight_kg:.3f}".replace('.', ' целых ') + " килограмм."
                else:
                    text = f"{weight_kg} килограмм."
                self.queue.put(text)
            except Exception:
                pass

    def stop(self):
        self.running = False
        self.queue.put(None)
        self.thread.join(timeout=1.0)
