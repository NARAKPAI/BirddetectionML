#include "dl_image_define.hpp"
#include "driver/uart.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "espdet_detect.hpp"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <cstdio>
#include <cstring>


static const char *TAG = "pigeon_detect";

#define IMG_W 224
#define IMG_H 224
#define FRAME_BYTES (IMG_W * IMG_H * 2) // RGB565 = 100,352 bytes
#define UART_PORT UART_NUM_0
#define UART_BAUD 2000000

static void init_uart_fast(void) {
  uart_config_t uart_config = {};
  uart_config.baud_rate = UART_BAUD;
  uart_config.data_bits = UART_DATA_8_BITS;
  uart_config.parity = UART_PARITY_DISABLE;
  uart_config.stop_bits = UART_STOP_BITS_1;
  uart_config.flow_ctrl = UART_HW_FLOWCTRL_DISABLE;
  uart_config.source_clk = UART_SCLK_DEFAULT;

  uart_driver_install(UART_PORT, 16384, 0, 0, NULL, 0);
  uart_param_config(UART_PORT, &uart_config);
}

static void log_heap(const char *where) {
  ESP_LOGI(TAG, "[%s] free internal=%u KB, free psram=%u KB, stack_left=%u B",
           where,
           (unsigned)(heap_caps_get_free_size(MALLOC_CAP_INTERNAL) / 1024),
           (unsigned)(heap_caps_get_free_size(MALLOC_CAP_SPIRAM) / 1024),
           (unsigned)uxTaskGetStackHighWaterMark(NULL) * 4);
}

static void detect_task(void *arg) {
  ESP_LOGI(TAG, "Initializing ESPDetDetect Pigeon Model...");
  log_heap("before model");
  ESPDetDetect *detect = new ESPDetDetect();
  log_heap("after model");

  // Allocate 224x224 RGB565 buffer in Octal PSRAM
  uint8_t *rx_buf = (uint8_t *)heap_caps_malloc(
      FRAME_BYTES, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  if (!rx_buf) {
    ESP_LOGE(
        TAG,
        "Failed to allocate PSRAM buffer! Enable Octal PSRAM in menuconfig.");
    vTaskDelete(NULL);
    return;
  }
  memset(rx_buf, 0, FRAME_BYTES);

  dl::image::img_t img = {.data = rx_buf,
                          .width = IMG_W,
                          .height = IMG_H,
                          .pix_type = dl::image::DL_IMAGE_PIX_TYPE_RGB565BE};

  // 1. Dummy inference test on boot to verify model weights
  ESP_LOGI(TAG, "img.data=%p w=%d h=%d", img.data, (int)img.width,
           (int)img.height);
  log_heap("before self-test");
  ESP_LOGI(TAG, "Running boot self-test inference...");
  auto &boot_res = detect->run(img);
  ESP_LOGI(TAG,
           "Boot self-test passed! Detected %d objects. Ready for PC stream @ "
           "%d baud.",
           (int)boot_res.size(), UART_BAUD);
  log_heap("after self-test");

  init_uart_fast();

  // 2. Main loop: wait for header [0xAA, 0x55] + 100,352 bytes RGB565 frame
  uint8_t hdr[2];
  while (true) {
    int len = uart_read_bytes(UART_PORT, &hdr[0], 1, portMAX_DELAY);
    if (len == 1 && hdr[0] == 0xAA) {
      len = uart_read_bytes(UART_PORT, &hdr[1], 1, pdMS_TO_TICKS(50));
      if (len == 1 && hdr[1] == 0x55) {
        int received = 0;
        while (received < FRAME_BYTES) {
          int r = uart_read_bytes(UART_PORT, rx_buf + received,
                                  FRAME_BYTES - received, pdMS_TO_TICKS(500));
          if (r <= 0)
            break;
          received += r;
        }
        if (received == FRAME_BYTES) {
          auto &results = detect->run(img);
          if (results.empty()) {
            printf("RES:NONE\n");
          } else {
            for (const auto &res : results) {
              printf("RES:PIGEON,%.2f,%d,%d,%d,%d\n", res.score, res.box[0],
                     res.box[1], res.box[2], res.box[3]);
            }
          }
          fflush(stdout);
        }
      }
    }
  }
}

extern "C" void app_main(void) {
  // Run everything in a task with a big stack (esp-dl inference needs a lot)
  xTaskCreatePinnedToCore(detect_task, "detect_task", 32 * 1024, NULL, 5, NULL,
                          1);
}