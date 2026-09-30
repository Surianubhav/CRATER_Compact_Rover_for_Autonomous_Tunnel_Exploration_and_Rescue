import base64
import cv2
import numpy as np
from pathlib import Path
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from ultralytics import YOLO

app = FastAPI(title="MINEGUARD Thermal Detection API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set path directly to your SIH folder model
MODEL_PATH = Path(r"C:\Users\click\Downloads\SIH\thermal-human-detection\models\yolov8_thermal_best.pt")

# Verify file existence before loading
if not MODEL_PATH.exists():
    raise FileNotFoundError(
        f"Could not find model file at: {MODEL_PATH}\n"
        "Please check the folder path and ensure yolov8_thermal_best.pt exists."
    )

model = YOLO(str(MODEL_PATH))

@app.post("/api/detect-thermal")
async def detect_thermal(file: UploadFile = File(...)):
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    results = model(image, conf=0.25)
    result = results[0]

    detections = []
    annotated_frame = result.plot()

    for box in result.boxes:
        conf = float(box.conf[0])
        cls = int(box.cls[0])
        label = model.names[cls]
        detections.append({
            "label": label,
            "confidence": round(conf, 4)
        })

    _, buffer = cv2.imencode('.jpg', annotated_frame)
    base64_image = base64.b64encode(buffer).decode('utf-8')
    image_url = f"data:image/jpeg;base64,{base64_image}"

    highest_confidence = max([d['confidence'] for d in detections], default=0.0)

    return {
        "detected": len(detections) > 0,
        "count": len(detections),
        "confidence": highest_confidence,
        "detections": detections,
        "image_data": image_url
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)