// ESP32-CAM (AI-Thinker) -> AVI video recorder to SD card
// - Writes real .avi files (MJPEG inside) with correct fps + index, so they
//   play directly in VLC / Windows Media Player / phones. No raw .mjpeg.
// - Robust SD mount (tries several modes)
// - Flash LED kept ON
// - New file every SEGMENT_SECONDS
// - Stop button on GPIO13 (to GND) closes the file cleanly
//
// Note: the ESP32 has no H.264 encoder, so true H.264 .mp4 is not possible
// on the board. Convert on your PC if you need .mp4:
//   ffmpeg -i video_0000.avi -c:v libx264 -pix_fmt yuv420p -crf 23 video_0000.mp4

#include "esp_camera.h"
#include "FS.h"
#include "SD_MMC.h"
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"

// ---------- AI-Thinker ESP32-CAM pins ----------
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// ---------- Settings ----------
#define FLASH_LED_PIN      4      // onboard flash LED
#define STOP_BTN_PIN      13      // button between GPIO13 and GND
#define SEGMENT_SECONDS   60      // new file every N seconds
#define FLUSH_EVERY_N     30      // flush to SD every N frames
#define LED_BRIGHTNESS   255      // 0-255. Lower (e.g. 60) = cooler LED (uses PWM)
#define MAX_FRAMES      2000      // max frames per file (index kept in RAM)

// ---------- AVI state ----------
#define AVI_HEADER_SIZE 224

File videoFile;
uint32_t frameCount = 0;
uint32_t segmentStart = 0;
uint32_t moviBytes = 0;       // total bytes of frame chunks
uint32_t filePos = 0;         // current write position in file
uint32_t maxFrameSize = 0;
uint16_t frameW = 640, frameH = 480;
uint32_t idxOffset[MAX_FRAMES];
uint32_t idxSize[MAX_FRAMES];
int fileIndex = 0;
bool recording = false;
bool ready = false;

// ---------- Little-endian helpers ----------
static void w32(uint8_t *b, int &p, uint32_t v) { memcpy(b + p, &v, 4); p += 4; }
static void w16(uint8_t *b, int &p, uint16_t v) { memcpy(b + p, &v, 2); p += 2; }
static void wTag(uint8_t *b, int &p, const char *t) { memcpy(b + p, t, 4); p += 4; }

// Builds the 224-byte AVI header. Called once as a placeholder, and again
// at close time with the real frame count / fps / sizes.
void buildHeader(uint8_t *h, uint32_t frames, uint32_t fpsX1000) {
  if (fpsX1000 == 0) fpsX1000 = 10000;
  uint32_t usPerFrame = (uint32_t)(1000000000ULL / fpsX1000);
  uint32_t fileSize = AVI_HEADER_SIZE + moviBytes + 8 + frames * 16;
  int p = 0;

  wTag(h, p, "RIFF"); w32(h, p, fileSize - 8); wTag(h, p, "AVI ");
  wTag(h, p, "LIST"); w32(h, p, 192);          wTag(h, p, "hdrl");

  // Main AVI header
  wTag(h, p, "avih"); w32(h, p, 56);
  w32(h, p, usPerFrame);        // dwMicroSecPerFrame
  w32(h, p, 0);                 // dwMaxBytesPerSec
  w32(h, p, 0);                 // dwPaddingGranularity
  w32(h, p, 0x10);              // dwFlags: AVIF_HASINDEX
  w32(h, p, frames);            // dwTotalFrames
  w32(h, p, 0);                 // dwInitialFrames
  w32(h, p, 1);                 // dwStreams
  w32(h, p, maxFrameSize);      // dwSuggestedBufferSize
  w32(h, p, frameW);            // dwWidth
  w32(h, p, frameH);            // dwHeight
  w32(h, p, 0); w32(h, p, 0); w32(h, p, 0); w32(h, p, 0);  // reserved

  // Stream list
  wTag(h, p, "LIST"); w32(h, p, 116); wTag(h, p, "strl");

  // Stream header
  wTag(h, p, "strh"); w32(h, p, 56);
  wTag(h, p, "vids");           // fccType
  wTag(h, p, "MJPG");           // fccHandler
  w32(h, p, 0);                 // dwFlags
  w16(h, p, 0); w16(h, p, 0);   // wPriority, wLanguage
  w32(h, p, 0);                 // dwInitialFrames
  w32(h, p, 1000);              // dwScale
  w32(h, p, fpsX1000);          // dwRate  (rate/scale = fps)
  w32(h, p, 0);                 // dwStart
  w32(h, p, frames);            // dwLength
  w32(h, p, maxFrameSize);      // dwSuggestedBufferSize
  w32(h, p, 0xFFFFFFFF);        // dwQuality
  w32(h, p, 0);                 // dwSampleSize
  w16(h, p, 0); w16(h, p, 0); w16(h, p, frameW); w16(h, p, frameH);  // rcFrame

  // Stream format (BITMAPINFOHEADER)
  wTag(h, p, "strf"); w32(h, p, 40);
  w32(h, p, 40);                // biSize
  w32(h, p, frameW);            // biWidth
  w32(h, p, frameH);            // biHeight
  w16(h, p, 1);                 // biPlanes
  w16(h, p, 24);                // biBitCount
  wTag(h, p, "MJPG");           // biCompression
  w32(h, p, (uint32_t)frameW * frameH * 3);  // biSizeImage
  w32(h, p, 0); w32(h, p, 0);   // biXPelsPerMeter, biYPelsPerMeter
  w32(h, p, 0); w32(h, p, 0);   // biClrUsed, biClrImportant

  // Start of frame data
  wTag(h, p, "LIST"); w32(h, p, moviBytes + 4); wTag(h, p, "movi");
}

// ---------- SD mount with fallbacks ----------
bool mountSD() {
  // 1) 1-bit mode, default speed (keeps GPIO4 free for the flash LED)
  if (SD_MMC.begin("/sdcard", true)) { Serial.println("SD OK: 1-bit, default"); return true; }
  SD_MMC.end();

  // 2) 1-bit mode, slow probing speed for picky cards
  if (SD_MMC.begin("/sdcard", true, false, SDMMC_FREQ_PROBING)) { Serial.println("SD OK: 1-bit, slow"); return true; }
  SD_MMC.end();

  // 3) 4-bit mode (uses GPIO4, so the flash LED will glow/flicker during writes)
  if (SD_MMC.begin("/sdcard", false)) { Serial.println("SD OK: 4-bit (LED may flicker)"); return true; }
  SD_MMC.end();

  return false;
}

// ---------- Camera ----------
bool initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  if (psramFound()) {
    config.frame_size = FRAMESIZE_VGA;      // 640x480; try FRAMESIZE_SVGA for more detail
    config.jpeg_quality = 12;               // lower = better quality, bigger files
    config.fb_count = 2;
    config.grab_mode = CAMERA_GRAB_LATEST;
  } else {
    config.frame_size = FRAMESIZE_QVGA;
    config.jpeg_quality = 15;
    config.fb_count = 1;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
    return false;
  }

  // Read the real frame size for the AVI header
  camera_fb_t *fb = esp_camera_fb_get();
  if (fb) {
    frameW = fb->width;
    frameH = fb->height;
    esp_camera_fb_return(fb);
  }
  return true;
}

// ---------- Flash LED ----------
void ledOn() {
  if (LED_BRIGHTNESS >= 255) {
    pinMode(FLASH_LED_PIN, OUTPUT);
    digitalWrite(FLASH_LED_PIN, HIGH);
  } else {
    analogWrite(FLASH_LED_PIN, LED_BRIGHTNESS);
  }
}

void ledOff() {
  pinMode(FLASH_LED_PIN, OUTPUT);
  digitalWrite(FLASH_LED_PIN, LOW);
}

// ---------- AVI file handling ----------
// Finishes the file: writes the index, then rewrites the header with the
// real frame count and measured fps.
void closeAvi() {
  if (!videoFile) return;

  // idx1 index chunk
  uint8_t chunk[16];
  int p = 0;
  wTag(chunk, p, "idx1");
  w32(chunk, p, frameCount * 16);
  videoFile.write(chunk, 8);
  for (uint32_t i = 0; i < frameCount; i++) {
    p = 0;
    wTag(chunk, p, "00dc");
    w32(chunk, p, 0x10);            // AVIIF_KEYFRAME (every JPEG is a keyframe)
    w32(chunk, p, idxOffset[i]);
    w32(chunk, p, idxSize[i]);
    videoFile.write(chunk, 16);
  }

  // Measured fps -> correct playback speed
  uint32_t elapsedMs = millis() - segmentStart;
  if (elapsedMs == 0) elapsedMs = 1;
  uint32_t fpsX1000 = (uint32_t)((uint64_t)frameCount * 1000000ULL / elapsedMs);
  Serial.printf("Segment done: %u frames, %.1f fps\n", frameCount, fpsX1000 / 1000.0);

  // Rewrite the real header at the start of the file
  uint8_t hdr[AVI_HEADER_SIZE];
  buildHeader(hdr, frameCount, fpsX1000);
  videoFile.seek(0);
  videoFile.write(hdr, AVI_HEADER_SIZE);
  videoFile.flush();
  videoFile.close();
}

bool openNewFile() {
  char path[32];
  do {
    snprintf(path, sizeof(path), "/video_%04d.avi", fileIndex++);
  } while (SD_MMC.exists(path));

  videoFile = SD_MMC.open(path, FILE_WRITE);
  if (!videoFile) {
    Serial.println("Failed to open file on SD card");
    return false;
  }

  frameCount = 0;
  moviBytes = 0;
  maxFrameSize = 0;

  // Placeholder header (overwritten with real values on close)
  uint8_t hdr[AVI_HEADER_SIZE];
  buildHeader(hdr, 0, 10000);
  videoFile.write(hdr, AVI_HEADER_SIZE);
  filePos = AVI_HEADER_SIZE;

  segmentStart = millis();
  Serial.printf("Recording to %s\n", path);
  return true;
}

// Writes one JPEG frame as an AVI "00dc" chunk
bool writeFrame(camera_fb_t *fb) {
  if (frameCount >= MAX_FRAMES) return false;

  uint32_t len = fb->len;
  uint32_t pad = len & 1;                       // chunks are 2-byte aligned
  uint8_t ch[8];
  int p = 0;
  wTag(ch, p, "00dc");
  w32(ch, p, len);

  idxOffset[frameCount] = filePos - (AVI_HEADER_SIZE - 4);  // relative to "movi"
  idxSize[frameCount] = len;

  if (videoFile.write(ch, 8) != 8) return false;
  if (videoFile.write(fb->buf, len) != len) return false;
  if (pad) { uint8_t z = 0; videoFile.write(&z, 1); }

  filePos += 8 + len + pad;
  moviBytes += 8 + len + pad;
  if (len > maxFrameSize) maxFrameSize = len;
  frameCount++;
  return true;
}

void stopRecording(const char *reason) {
  closeAvi();
  recording = false;
  ledOff();  // LED off = safe to remove SD card
  Serial.printf("Recording stopped (%s). Safe to remove SD card.\n", reason);
}

// ---------- Setup ----------
void setup() {
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);  // disable brownout reset
  Serial.begin(115200);
  delay(500);

  if (!mountSD()) {
    Serial.println("SD card mount failed in all modes");
    return;
  }
  if (SD_MMC.cardType() == CARD_NONE) {
    Serial.println("No SD card attached");
    return;
  }
  Serial.printf("SD size: %llu MB\n", SD_MMC.cardSize() / (1024 * 1024));

  if (!initCamera()) return;

  // Set AFTER SD init, because GPIO4 is shared with the SD card
  ledOn();
  pinMode(STOP_BTN_PIN, INPUT_PULLUP);

  if (!openNewFile()) return;

  recording = true;
  ready = true;
}

// ---------- Main loop ----------
void loop() {
  if (!ready || !recording) { delay(100); return; }

  // Stop button (with simple debounce)
  if (digitalRead(STOP_BTN_PIN) == LOW) {
    delay(30);
    if (digitalRead(STOP_BTN_PIN) == LOW) {
      stopRecording("button");
      return;
    }
  }

  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Frame capture failed");
    return;
  }

  bool ok = writeFrame(fb);
  esp_camera_fb_return(fb);

  if (!ok) {
    stopRecording("SD write error or frame limit");
    return;
  }

  if (frameCount % FLUSH_EVERY_N == 0) videoFile.flush();

  // Start a new file every SEGMENT_SECONDS (or when the frame index is full)
  if (millis() - segmentStart >= SEGMENT_SECONDS * 1000UL || frameCount >= MAX_FRAMES) {
    closeAvi();
    if (!openNewFile()) {
      stopRecording("could not open next file");
      return;
    }
  }

  ledOn();  // keep the flash LED on
}