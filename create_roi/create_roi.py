import cv2
import numpy as np
import sys
import os
import yaml
import logging

# Настройка базового логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ========== ПАРАМЕТРЫ ==========
# URL камеры - ЗАМЕНИТЕ НА ВАШ URL
RTSP_URL = "rtsp://77.221.215.25:556/user=admin&password=s255636S&channel=1&stream=1?.sdp"

# =====================================

def select_roi(frame):
    """
    Открывает окно с оригинальным размером кадра для выбора ROI.
    Возвращает список с координатами вершин полигона.
    """
    if frame is None:
        logging.error("Кадр для выбора ROI не был получен.")
        return None

    # Получаем оригинальные размеры кадра
    original_h, original_w = frame.shape[:2]
    
    # Всегда используем оригинальный размер для отображения
    display_width = original_w
    display_height = original_h
    display_frame = frame.copy()
    
    # Предупреждаем пользователя, если изображение слишком большое
    screen_width = 1920  # Предполагаемая ширина экрана
    screen_height = 1080  # Предполагаемая высота экрана
    
    if original_w > screen_width or original_h > screen_height:
        logging.warning(f"Размер кадра ({original_w}x{original_h}) превышает размеры экрана ({screen_width}x{screen_height}).")
        logging.warning("Используйте колесико мыши для прокрутки или переместите окно.")
    
    points = []
    window_name = f'Select ROI ({display_width}x{display_height}) | ENTER - finish, R - reset, ESC - cancel'

    def mouse_callback(event, x, y, flags, param):
        """Обрабатывает клики мыши и сохраняет координаты."""
        nonlocal points
        if event == cv2.EVENT_LBUTTONDOWN:
            points.append((x, y))
            logging.info(f"Добавлена точка: ({x}, {y})")

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, display_width, display_height)
    cv2.setMouseCallback(window_name, mouse_callback)

    logging.info("Кликайте левой кнопкой мыши, чтобы задать вершины многоугольника ROI.")
    logging.info("Нажмите 'Enter', когда закончите.")
    logging.info("Нажмите 'R', чтобы сбросить точки.")
    logging.info("Нажмите 'ESC', чтобы отменить.")
    logging.info("Используйте колесико мыши для прокрутки, если изображение не помещается на экране.")

    while True:
        # Копируем кадр для рисования, чтобы не изменять исходный
        current_display = display_frame.copy()

        # Рисуем точки и линии поверх кадра
        if len(points) > 0:
            for i in range(len(points)):
                cv2.circle(current_display, points[i], 5, (0, 0, 255), -1)
                if i > 0:
                    cv2.line(current_display, points[i - 1], points[i], (0, 255, 0), 2)

        # Замыкаем полигон для наглядности, если точек больше двух
        if len(points) > 2:
            cv2.line(current_display, points[-1], points[0], (0, 255, 0), 2)

        cv2.imshow(window_name, current_display)

        key = cv2.waitKey(20) & 0xFF
        if key == 13:  # Enter
            if len(points) < 3:
                logging.warning("Нужно выбрать как минимум 3 точки для создания ROI.")
            else:
                logging.info("ROI успешно определен.")
                break
        elif key == ord('r'):  # 'R' для сброса
            points = []
            logging.info("Точки сброшены. Вы можете начать заново.")
        elif key == 27:  # ESC для выхода без сохранения
            logging.warning("Выбор ROI отменен.")
            points = []
            break

    cv2.destroyAllWindows()

    # Если точки не были выбраны, возвращаем None
    if not points:
        return None

    # Возвращаем точки в оригинальных координатах (без масштабирования)
    return points

def main():
    # Проверяем, указан ли URL
    if not RTSP_URL or RTSP_URL == "rtsp://your_camera_url_here":
        logging.error("Пожалуйста, укажите действительный RTSP URL в переменной RTSP_URL внутри кода.")
        sys.exit(1)

    logging.info(f"Попытка подключения к {RTSP_URL}...")

    # Настраиваем параметры подключения RTSP
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
    cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
    
    # Устанавливаем таймаут для подключения
    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000)

    if not cap.isOpened():
        logging.error("Не удалось открыть RTSP поток. Проверьте URL и доступность камеры.")
        sys.exit(1)

    # Получаем информацию о размере кадра
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    logging.info(f"Размер кадра из потока: {frame_width}x{frame_height}")

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        logging.error("Не удалось прочитать кадр из потока.")
        sys.exit(1)

    logging.info("Кадр успешно получен. Открываю окно для выбора ROI...")

    roi_points = select_roi(frame)

    if roi_points:
        # Выводим результат в требуемом формате
        print("\n" + "=" * 60)
        print("✅ ROI УСПЕШНО СОЗДАН!")
        print("=" * 60)
        print(f"ROI_POINTS={roi_points}")
        print("=" * 60)
        
        # Дополнительная информация
        print(f"\nРазмер оригинального кадра: {frame.shape[1]}x{frame.shape[0]}")
        print(f"Количество точек ROI: {len(roi_points)}")
        print("\nФормат для использования в коде:")
        print(f"ROI_POINTS = {roi_points}")
    else:
        logging.warning("ROI не был создан.")

if __name__ == "__main__":
    main()
