#!/usr/bin/env python3
import time
import os
import warnings

# [NEW] Подавление логов ONNX Runtime C++ перед импортом
os.environ["ORT_LOGGING_LEVEL"] = "3"  # 3 = ERROR

from system import ScaleSystem

# Подавляем предупреждения ONNX Runtime на уровне Python
warnings.filterwarnings('ignore', category=UserWarning, module='onnxruntime')

def main():
    print("--- Запуск системы контроля ---")
    system = ScaleSystem()
    
    try:
        while True:
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        pass
    finally:
        system.stop()

if __name__ == "__main__":
    main()
