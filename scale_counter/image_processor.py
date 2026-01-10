# image_processor.py
import cv2
import numpy as np

class ImageCorrector:
    def __init__(self, width, height, config):
        self.w = width
        self.h = height
        
        # Получаем параметры из конфига
        k1 = config.DIST_K1
        k2 = config.DIST_K2
        balance = config.DIST_BALANCE
        stretch_factor_v = config.DIST_STRETCH_V

        # Подготовка матриц камеры
        # Логика 1-в-1 из distorsion.py
        K = np.array([[self.w, 0, self.w / 2],
                      [0, self.w, self.h / 2],
                      [0, 0, 1]], dtype=np.float32)

        D = np.array([[k1], [k2], [0.0], [0.0]], dtype=np.float32)

        # Оценка новой матрицы камеры
        new_K = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(
            K, D, (self.w, self.h), np.eye(3), balance=balance
        )

        # Генерация карт искажения
        self.map_x, self.map_y = cv2.fisheye.initUndistortRectifyMap(
            K, D, np.eye(3), new_K, (self.w, self.h), cv2.CV_32FC1
        )

        # --- ОПТИМИЗАЦИЯ: Внедрение растяжения прямо в карты (Map Merging) ---
        if stretch_factor_v != 1.0:
            mid_height = self.h // 2
            # Генерируем координаты, которые мы хотим "достать" из исходника
            y_coords_source = np.linspace(mid_height, self.h - 1, int((self.h - mid_height) * stretch_factor_v))

            rows_needed = self.h - mid_height

            # Если stretch > 1, берем начало массива
            indices = y_coords_source[:rows_needed].astype(int)
            
            # Защита от выхода за границы индекса (на случай экстремальных значений stretch)
            indices = np.clip(indices, 0, self.h - 1)

            # Применяем подмену координат в картах
            self.map_x[mid_height:self.h, :] = self.map_x[indices, :]
            self.map_y[mid_height:self.h, :] = self.map_y[indices, :]

    def process(self, img):
        """Применяет заранее рассчитанный remap к изображению"""
        if img is None:
            return None
        # Единственная тяжелая операция с пикселями - remap
        return cv2.remap(img, self.map_x, self.map_y, interpolation=cv2.INTER_LINEAR)
