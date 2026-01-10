# detector.py
import cv2
import os
from ultralytics import YOLO

class YOLODetector:
    def __init__(self, config):
        self.config = config
        model_path = config.YOLO_MODEL_PATH
            
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Модель YOLO не найдена по пути: {model_path}")
        
        try:
            # Устанавливаем провайдер только для CPU чтобы избежать предупреждений о GPU
            providers = ['CPUExecutionProvider']
            self.model = YOLO(model_path, task='detect')
        except Exception as e:
            raise
        
        self.colors = {0: (0, 255, 0)}

    def detect_and_save(self, source_path, target_path):
        if not os.path.exists(source_path):
            return 0

        img = cv2.imread(source_path)
        if img is None:
            return 0
        
        try:
            results = self.model.predict(
                source=img,
                conf=self.config.YOLO_CONF_THRESH,
                classes=self.config.YOLO_CLASSES,
                verbose=False,
                task='detect'
            )
        except Exception as e:
            return 0
        
        detections = []
        for result in results:
            if result.boxes is not None:
                boxes = result.boxes.xyxy.cpu().numpy()
                confs = result.boxes.conf.cpu().numpy()
                clss = result.boxes.cls.cpu().numpy().astype(int)
                
                for box, conf, cls in zip(boxes, confs, clss):
                    detections.append((box, conf, cls))
                    
                    x1, y1, x2, y2 = map(int, box)
                    cv2.rectangle(img, (x1, y1), (x2, y2), self.colors.get(cls, (0, 255, 0)), 2)
                    
                    class_name = self.model.names.get(cls, f"Class_{cls}")
                    label = f"{class_name} {conf:.2f}"
                    cv2.putText(img, label, (x1, y1-10), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, self.colors.get(cls, (0, 255, 0)), 2)

        count_label = f"Count: {len(detections)}"
        cv2.putText(img, count_label, (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        cv2.imwrite(target_path, img)
        return len(detections)
