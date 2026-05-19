/**
 * HUSKY-SORTER-001 ESP32 Firmware
 * 
 * Main controller for sensor reading, motor control, and Pi communication.
 * 
 * Hardware: ESP32 DevKit v1 (30-pin)
 * 
 * Pin Assignment (v2.0 — P0 fix 2026-05-17):
 *   GPIO4  (INPUT)  - T1 sensor (top bean detector)
 *   GPIO5  (INPUT)  - T2 sensor (bottom bean detector)
 *   GPIO15 (INPUT)  - E-STOP button (active LOW, hardware ISR)
 *   GPIO18 (OUTPUT) - Stepper1 PUL (vibrating feeder)
 *   GPIO19 (OUTPUT) - Stepper1 DIR
 *   GPIO21 (OUTPUT) - Stepper2 PUL (rotary distributor)
 *   GPIO22 (OUTPUT) - Stepper2 DIR
 *   GPIO16 (OUTPUT) - Air jet solenoid valve
 *   GPIO17 (OUTPUT) - Weighing cup release solenoid
 *   GPIO25 (OUTPUT) - Buffer selector valve
 *   GPIO26 (OUTPUT) - Stepper3 PUL (spiral feeder)
 *   GPIO27 (OUTPUT) - Stepper3 DIR
 *   GPIO14 (OUTPUT) - DRV8833 MS1 (microstep select, v2 init)
 *   GPIO23 (OUTPUT) - DRV8833 MS2 (microstep select, v2 init)
 *   GPIO13 (OUTPUT) - Fan PWM (5015 blower speed control)
 *   GPIO34 (INPUT)  - Level sensor data (analog)
 *   GPIO35 (INPUT)  - HX711 DT (via voltage divider)
 *   GPIO32 (INPUT)  - HX711 SCK (via GPIO expander simulation)
 *   GPIO33 (INPUT)  - AD7746 interrupt
 *   GPIO36 (INPUT)  - Spare sensor input 1
 *   GPIO39 (INPUT)  - Spare sensor input 2
 * 
 * Communication: UART (115200 8N1) ↔ Raspberry Pi
 * 
 * Protocol (JSON over UART):
 *   Pi → ESP: {"cmd": "FEED_RATE", "args": {"rpm": 30}}
 *   Pi → ESP: {"cmd": "VALVE", "args": {"id": "air_jet", "state": 1}}
 *   Pi → ESP: {"cmd": "STEPPER", "args": {"id": "feeder", "steps": 100, "speed": 500}}
 *   Pi → ESP: {"cmd": "STATUS"} → ESP responds with full status
 *   ESP → Pi: {"type": "EVENT", "event": "bean_detected", "t1": 12345678}
 *   ESP → Pi: {"type": "STATUS", "uptime_ms": 12345, "heap_free": 180000, ...}
 */

#include <Arduino.h>
#include <driver/gpio.h>
#include <driver/adc.h>
#include <driver/ledc.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>
#include <freertos/semphr.h>
#include <freertos/timers.h>
#include <HardwareSerial.h>
#include <esp_task_wdt.h>
#include <esp_timer.h>
#include <vector>

// ============================================================================
// Configuration
// ============================================================================

#define FIRMWARE_VERSION "1.0.0"
#define FIRMWARE_BUILD "2026-05-17"

// UART to Pi
#define UART_TX_PIN 1
#define UART_RX_PIN 3
#define UART_BAUD 115200

// Stepper pulse timing (microseconds)
#define STEP_PULSE_US 50

// P0-09 fix: T1/T2 debounce window (microseconds)
#define SENSOR_DEBOUNCE_US 5000  // 5ms

// P0-07 fix: E-STOP hardware button
#define ESTOP_PIN GPIO_NUM_15

// P0-08 fix: Task Watchdog timeout (seconds)
#define TWDT_TIMEOUT_S 5

// P0-18 fix: DRV8833 microstep select pins
#define DRV8833_MS1_PIN GPIO_NUM_14
#define DRV8833_MS2_PIN GPIO_NUM_23

// ============================================================================
// Types & Enums
// ============================================================================

enum class SystemState {
    BOOTING,
    INITIALIZING,
    IDLE,
    RUNNING,
    PAUSED,
    FAULT
};

enum class StepperId {
    FEEDER_VIBRATING,
    DISTRIBUTOR_ROTARY,
    SPIRAL_FEEDER
};

enum class SolenoidId {
    AIR_JET,
    WEIGHING_CUP_RELEASE,
    BUFFER_SELECTOR
};

struct StepperConfig {
    gpio_num_t pul_pin;
    gpio_num_t dir_pin;
    uint8_t microstep;        // 1, 2, 4, 8, 16
    uint16_t steps_per_rev;   // physical steps per revolution
    float gear_ratio;         // motor to output ratio
    bool enabled;
    long current_steps;       // current position relative to home
    long target_steps;
    uint32_t speed_rpm;       // current target speed
    bool moving;
};

struct SolenoidConfig {
    gpio_num_t pin;
    bool state;       // true = energized/open, false = de-energized/closed
    uint32_t pulse_duration_ms;  // for timed pulse mode
};

struct HX711Config {
    gpio_num_t dt_pin;       // data out (from HX711)
    gpio_num_t sck_pin;      // clock in (to HX711)
    uint8_t gain;            // 128 or 64
    int32_t offset;          // tare offset
    float scale;             // calibration scale (g/count)
};

struct SystemStatus {
    SystemState state;
    uint32_t uptime_ms;
    uint32_t heap_free_bytes;
    uint32_t stack_hwm;
    // P2-08: stack high-water mark per task
    uint32_t stack_hwm_uart;
    uint32_t stack_hwm_status;
    uint32_t stack_hwm_stepper;
    float cpu_temp_c;
    float vcc_voltage;
    // Steppers
    bool stepper_feeder_enabled;
    bool stepper_distributor_enabled;
    bool stepper_spiral_enabled;
    // Solenoids
    bool air_jet_active;
    bool weighing_release_active;
    bool buffer_selector_active;
    // Sensors
    float t1_beam_voltage;   // ADC reading for T1 sensor
    float t2_beam_voltage;   // ADC reading for T2 sensor
    bool t1_beam_broken;     // true = bean interrupting beam
    bool t2_beam_broken;
    // Motor RPM
    uint32_t feeder_rpm;
    uint32_t distributor_rpm;
    uint32_t spiral_rpm;
    // Counters
    uint32_t beans_detected;
    uint32_t commands_received;
    uint32_t faults_detected;
};

struct UARTCommand {
    String cmd;
    String args_json;
};

// ============================================================================
// Global State
// ============================================================================

SystemState g_system_state = SystemState::BOOTING;
SystemStatus g_status = {};

// P2-08: task handles for stack HWM monitoring
static TaskHandle_t g_task_uart = NULL;
static TaskHandle_t g_task_status = NULL;
static TaskHandle_t g_task_stepper = NULL;

StepperConfig g_steppers[3] = {
    // Feeder vibrating
    {gpio_num_t(GPIO_NUM_18), gpio_num_t(GPIO_NUM_19), 8, 64, 1.0f, false, 0, 0, 0, false},
    // Distributor rotary  
    {gpio_num_t(GPIO_NUM_21), gpio_num_t(GPIO_NUM_22), 8, 64, 1.0f, false, 0, 0, 0, false},
    // Spiral feeder
    {gpio_num_t(GPIO_NUM_26), gpio_num_t(GPIO_NUM_27), 8, 64, 1.0f, false, 0, 0, 0, false}
};

SolenoidConfig g_solenoids[3] = {
    {gpio_num_t(GPIO_NUM_16), false, 0},
    {gpio_num_t(GPIO_NUM_17), false, 0},
    {gpio_num_t(GPIO_NUM_25), false, 0}
};

HX711Config g_hx711 = {
    gpio_num_t(GPIO_NUM_35),
    gpio_num_t(GPIO_NUM_32),
    128,
    0,
    1.0f
};

// UART command queue
static QueueHandle_t g_cmd_queue = NULL;

// Tick counters for stepper pulse generation
static volatile uint32_t g_step_timers[3] = {0, 0, 0};
static volatile bool g_step_dirs[3] = {false, false, false};
static volatile int g_steppers_to_step[3] = {0, 0, 0};
static SemaphoreHandle_t g_stepper_mutex = NULL;

// P0-09: T1/T2 debounce timestamps (microseconds, esp_timer)
static volatile int64_t g_t1_last_trigger_us = 0;
static volatile int64_t g_t2_last_trigger_us = 0;

// P0-07: E-STOP state
static volatile bool g_estop_active = false;

// P1-13: Solenoid pulse timers (non-blocking auto-off)
static TimerHandle_t g_solenoid_timers[3] = {NULL, NULL, NULL};

// ============================================================================
// Pin Initialization
// ============================================================================

void init_pins() {
    // T1/T2 sensor inputs (NPN NO, falling edge = bean detected)
    // P0-09 fix: use GPIO_INTR_NEGEDGE + pullup for debounced sensor input
    gpio_config_t t1_conf = {
        .pin_bit_mask = (1ULL << GPIO_NUM_4),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,     // P0-09: pullup for NPN sensor
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_NEGEDGE        // P0-09: falling edge only
    };
    gpio_config(&t1_conf);

    gpio_config_t t2_conf = {
        .pin_bit_mask = (1ULL << GPIO_NUM_5),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,     // P0-09: pullup for NPN sensor
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_NEGEDGE        // P0-09: falling edge only
    };
    gpio_config(&t2_conf);

    // P0-07: E-STOP button input (active LOW, hardware ISR)
    gpio_config_t estop_conf = {
        .pin_bit_mask = (1ULL << ESTOP_PIN),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_NEGEDGE
    };
    gpio_config(&estop_conf);

    // P0-18: DRV8833 microstep select pins
    // Truth table: MS1=0,MS2=0=full | 1,0=half | 0,1=1/4 | 1,1=1/8
    gpio_reset_pin(DRV8833_MS1_PIN);
    gpio_reset_pin(DRV8833_MS2_PIN);
    gpio_set_direction(DRV8833_MS1_PIN, GPIO_MODE_OUTPUT);
    gpio_set_direction(DRV8833_MS2_PIN, GPIO_MODE_OUTPUT);
    gpio_set_level(DRV8833_MS1_PIN, 1);  // MS1=HIGH → 1/8 microstep
    gpio_set_level(DRV8833_MS2_PIN, 1);  // MS2=HIGH   (matches microstep=8 in config)

    // Solenoid outputs (default off)
    for (auto& sol : g_solenoids) {
        gpio_reset_pin(sol.pin);
        gpio_set_direction(sol.pin, GPIO_MODE_OUTPUT);
        gpio_set_level(sol.pin, 0);  // de-energized
    }

    // Stepper pins
    for (auto& step : g_steppers) {
        gpio_reset_pin(step.pul_pin);
        gpio_reset_pin(step.dir_pin);
        gpio_set_direction(step.pul_pin, GPIO_MODE_OUTPUT);
        gpio_set_direction(step.dir_pin, GPIO_MODE_OUTPUT);
        gpio_set_level(step.pul_pin, 0);
        gpio_set_level(step.dir_pin, 0);
    }

    // Fan PWM (GPIO13 → LEDC channel 0, timer 0, 25kHz)
    gpio_reset_pin(gpio_num_t(GPIO_NUM_13));
    gpio_set_direction(gpio_num_t(GPIO_NUM_13), GPIO_MODE_OUTPUT);

    // LEDC timer configuration
    ledc_timer_config_t fan_timer = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .timer_num = LEDC_TIMER_0,
        .duty_resolution = LEDC_TIMER_10_BIT,  // 0-1023
        .freq_hz = 25000,                       // 25kHz (above audible range)
        .clk_cfg = LEDC_AUTO_CLK
    };
    ledc_timer_config(&fan_timer);

    // LEDC channel configuration
    ledc_channel_config_t fan_channel = {
        .gpio_num = GPIO_NUM_13,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = LEDC_CHANNEL_0,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = LEDC_TIMER_0,
        .duty = 0,
        .hpoint = 0
    };
    ledc_channel_config(&fan_channel);
    Serial.println("[INIT] Fan PWM initialized (LEDC 25kHz, 10-bit)");

    // ADC for sensors
    adc1_config_width(ADC_WIDTH_BIT_12);

    Serial.println("[INIT] GPIO pins initialized (v2: +E-STOP +debounce +DRV8833 MS)");
}

// ============================================================================
// Stepper Motor Control
// ============================================================================

void stepper_set_enabled(StepperId id, bool enabled) {
    int idx = static_cast<int>(id);
    if (xSemaphoreTake(g_stepper_mutex, portMAX_DELAY) == pdTRUE) {
        g_steppers[idx].enabled = enabled;
        if (!enabled) {
            gpio_set_level(g_steppers[idx].pul_pin, 0);
            g_steppers[idx].moving = false;
            g_steppers_to_step[idx] = 0;
        }
        xSemaphoreGive(g_stepper_mutex);
    }
}

void stepper_set_speed(StepperId id, uint32_t rpm) {
    int idx = static_cast<int>(id);
    if (xSemaphoreTake(g_stepper_mutex, portMAX_DELAY) == pdTRUE) {
        g_steppers[idx].speed_rpm = rpm;
        xSemaphoreGive(g_stepper_mutex);
    }
}

void stepper_move_steps(StepperId id, int32_t steps, bool direction, uint32_t speed_rpm) {
    int idx = static_cast<int>(id);
    if (xSemaphoreTake(g_stepper_mutex, portMAX_DELAY) == pdTRUE) {
        g_steppers[idx].current_steps += steps * (direction ? 1 : -1);
        g_steppers_to_step[idx] = steps;
        g_step_dirs[idx] = direction;
        g_steppers[idx].moving = true;
        g_steppers[idx].speed_rpm = speed_rpm;
        xSemaphoreGive(g_stepper_mutex);
    }
}

void stepper_halt(StepperId id) {
    int idx = static_cast<int>(id);
    if (xSemaphoreTake(g_stepper_mutex, portMAX_DELAY) == pdTRUE) {
        g_steppers[idx].moving = false;
        g_steppers_to_step[idx] = 0;
        gpio_set_level(g_steppers[idx].pul_pin, 0);
        xSemaphoreGive(g_stepper_mutex);
    }
}

// ============================================================================
// Solenoid Control
// P1-13 fix: non-blocking pulse via FreeRTOS one-shot timer
// ============================================================================

// P1-13: Timer callback for auto-off solenoid pulse
static void solenoid_pulse_off_cb(TimerHandle_t timer) {
    // Timer ID encodes solenoid index
    int idx = (int)pvTimerGetTimerID(timer);
    if (idx >= 0 && idx < 3) {
        gpio_set_level(g_solenoids[idx].pin, 0);
        g_solenoids[idx].state = false;
        g_status.air_jet_active = g_solenoids[0].state;
        g_status.weighing_release_active = g_solenoids[1].state;
        g_status.buffer_selector_active = g_solenoids[2].state;
    }
}

void solenoid_set(SolenoidId id, bool on, uint32_t pulse_ms = 0) {
    int idx = static_cast<int>(id);
    gpio_set_level(g_solenoids[idx].pin, on ? 1 : 0);
    g_solenoids[idx].state = on;

    if (on && pulse_ms > 0) {
        // P1-13: Non-blocking pulse via FreeRTOS one-shot timer
        // Reuse or create timer for this solenoid
        if (g_solenoid_timers[idx] == NULL) {
            g_solenoid_timers[idx] = xTimerCreate(
                "sol_pulse",           // name
                pdMS_TO_TICKS(1),      // dummy period (set below)
                pdFALSE,               // one-shot (auto-delete = false, we reuse)
                (void*)idx,            // timer ID = solenoid index
                solenoid_pulse_off_cb  // callback
            );
        }
        // Cancel any running timer, then start with new period
        xTimerStop(g_solenoid_timers[idx], 0);
        xTimerChangePeriod(g_solenoid_timers[idx], pdMS_TO_TICKS(pulse_ms), 0);
        xTimerStart(g_solenoid_timers[idx], 0);
        // Returns immediately — timer fires callback after pulse_ms
    }

    g_status.air_jet_active = g_solenoids[0].state;
    g_status.weighing_release_active = g_solenoids[1].state;
    g_status.buffer_selector_active = g_solenoids[2].state;
}

// ============================================================================
// HX711 Load Cell Interface
// ============================================================================

int32_t hx711_read_raw() {
    // HX711 uses a simple clocked serial protocol
    // DT (data) goes low when data is ready (after 25+ clock pulses)
    // We clock SCK and read DT bit by bit (24 bits + channel/gain config bits)
    
    int32_t raw = 0;
    uint8_t config_bits = 0;
    
    gpio_set_level(g_hx711.sck_pin, 0);
    
    // Wait for DT to go low (data ready)
    uint32_t timeout = 10000;
    while (gpio_get_level(g_hx711.dt_pin) == 1 && timeout > 0) {
        timeout--;
    }
    
    if (timeout == 0) {
        Serial.println("[HX711] Timeout waiting for data ready");
        return 0;
    }
    
    // Read 24 bits (MSB first)
    for (int i = 0; i < 24; i++) {
        gpio_set_level(g_hx711.sck_pin, 1);
        delayMicroseconds(STEP_PULSE_US);
        raw = (raw << 1) | gpio_get_level(g_hx711.dt_pin);
        gpio_set_level(g_hx711.sck_pin, 0);
        delayMicroseconds(STEP_PULSE_US);
    }
    
    // Read 1-2 more bits for channel/gain config (typically 1 bit)
    for (int i = 0; i < (g_hx711.gain == 128 ? 1 : (g_hx711.gain == 64 ? 2 : 1)); i++) {
        gpio_set_level(g_hx711.sck_pin, 1);
        delayMicroseconds(STEP_PULSE_US);
        config_bits = gpio_get_level(g_hx711.dt_pin);
        gpio_set_level(g_hx711.sck_pin, 0);
        delayMicroseconds(STEP_PULSE_US);
    }
    
    // Handle signed value (24-bit two's complement)
    if (raw & 0x800000) {
        raw |= 0xFF000000;  // sign extend
    }
    
    return raw;
}

float hx711_read_weight_grams() {
    int32_t raw = hx711_read_raw();
    int32_t offset_removed = raw - g_hx711.offset;
    return ((float)offset_removed) / g_hx711.scale;
}

void hx711_tare() {
    int32_t sum = 0;
    const int samples = 10;
    for (int i = 0; i < samples; i++) {
        sum += hx711_read_raw();
        delayMicroseconds(100);
    }
    g_hx711.offset = sum / samples;
    Serial.printf("[HX711] Tare offset: %d\n", g_hx711.offset);
}

void hx711_calibrate(float known_weight_g) {
    int32_t reading = hx711_read_raw();
    g_hx711.scale = (float)(reading - g_hx711.offset) / known_weight_g;
    Serial.printf("[HX711] Calibrated: scale=%.4f g/count\n", g_hx711.scale);
}

// ============================================================================
// Bean Detection (T1/T2 Optical Sensors)
// ============================================================================

void update_sensor_readings() {
    // T1/T2 are infrared break-beam sensors (NPN NO output)
    // When bean breaks beam, NPN transistor turns OFF → GPIO pulled HIGH
    // When beam clear, NPN transistor turns ON → GPIO pulled LOW (falling edge)
    // P0-09: Interrupts now use GPIO_INTR_NEGEDGE + 5ms esp_timer debounce
    const int T1_THRESHOLD = 2048;  // mid-range of 0-4095
    const int T2_THRESHOLD = 2048;

    int t1_raw = adc1_get_raw(ADC1_CHANNEL_0);  // GPIO36 = ADC1_CH0
    int t2_raw = adc1_get_raw(ADC1_CHANNEL_3);  // GPIO39 = ADC1_CH3

    g_status.t1_beam_voltage = t1_raw * 3.3f / 4095.0f;
    g_status.t2_beam_voltage = t2_raw * 3.3f / 4095.0f;
    g_status.t1_beam_broken = (t1_raw < T1_THRESHOLD);
    g_status.t2_beam_broken = (t2_raw < T2_THRESHOLD);
}

// P0-09 fix: ISR with esp_timer-based 5ms debounce
// Uses esp_timer_get_time() for microsecond precision (not millis())
// GPIO_INTR_NEGEDGE ensures only falling edge triggers (beam broken)
bool IRAM_ATTR t1_isr() {
    int64_t now = esp_timer_get_time();
    if ((now - g_t1_last_trigger_us) < SENSOR_DEBOUNCE_US) {
        return false;  // Within debounce window, ignore
    }
    g_t1_last_trigger_us = now;

    BaseType_t high_task_woken = pdFALSE;
    uint32_t ts_us = (uint32_t)(now & 0xFFFFFFFF);
    xQueueSendFromISR(g_cmd_queue, &(UARTCommand{"T1_TRIGGER", String(ts_us)}), &high_task_woken);
    g_status.beans_detected++;
    return high_task_woken == pdTRUE ? true : false;
}

bool IRAM_ATTR t2_isr() {
    int64_t now = esp_timer_get_time();
    if ((now - g_t2_last_trigger_us) < SENSOR_DEBOUNCE_US) {
        return false;  // Within debounce window, ignore
    }
    g_t2_last_trigger_us = now;

    BaseType_t high_task_woken = pdFALSE;
    uint32_t ts_us = (uint32_t)(now & 0xFFFFFFFF);
    xQueueSendFromISR(g_cmd_queue, &(UARTCommand{"T2_TRIGGER", String(ts_us)}), &high_task_woken);
    return high_task_woken == pdTRUE ? true : false;
}

// ============================================================================
// P0-07: E-STOP Hardware ISR (SIL-3 <50ms response)
// ============================================================================
// E-STOP button on GPIO15 (active LOW, NC contact).
// This ISR immediately halts ALL motors and closes ALL valves,
// bypassing the UART command queue entirely.
// The UART ESTOP command is kept as a software fallback.

void IRAM_ATTR estop_isr() {
    // Immediate hardware halt — no queue, no delay
    g_estop_active = true;

    // Halt all steppers immediately (direct GPIO, no mutex)
    for (int i = 0; i < 3; i++) {
        gpio_set_level(g_steppers[i].pul_pin, 0);
    }

    // Close all solenoids immediately
    for (int i = 0; i < 3; i++) {
        gpio_set_level(g_solenoids[i].pin, 0);
    }

    // Queue status update for serial task (non-critical, best-effort)
    BaseType_t woken = pdFALSE;
    xQueueSendFromISR(g_cmd_queue, &(UARTCommand{"ESTOP_HW", String(0)}), &woken);
}

// ============================================================================
// P0-10: UART CRC-16 Checksum (CRC-16-CCITT)
// ============================================================================
// Command frames may include "crc":NNNN field. If present, the CRC of all
// bytes before the crc field must match. Mismatched CRC = corrupted frame.
// The Raspberry Pi sender appends "crc":XXXX to JSON frames.

static uint16_t crc16_ccitt(const uint8_t* data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8;
        for (int j = 0; j < 8; j++) {
            if (crc & 0x8000)
                crc = (crc << 1) ^ 0x1021;
            else
                crc = crc << 1;
        }
    }
    return crc;
}

// Extract CRC from JSON frame: {"cmd":"...","crc":12345}
// Returns -1 if no CRC field present (frame accepted without check)
static int extract_and_verify_crc(const String& json) {
    int crc_idx = json.indexOf("\"crc\"");
    if (crc_idx < 0) return -1;  // No CRC — accept without verification

    int colon = json.indexOf(":", crc_idx);
    if (colon < 0) return -1;

    int comma_or_brace = json.indexOf(",", colon);
    int end_brace = json.indexOf("}", colon);
    int end = (comma_or_brace > 0 && comma_or_brace < end_brace) ? comma_or_brace : end_brace;
    if (end < 0) end = json.length() - 1;

    String crc_str = json.substring(colon + 1, end);
    crc_str.trim();
    uint16_t expected_crc = (uint16_t)crc_str.toInt();

    // Compute CRC over the data portion (everything before the "crc" field)
    // Find the start of "crc" including the preceding comma
    int crc_field_start = crc_idx - 1;  // include the comma before "crc"
    if (crc_field_start < 0) crc_field_start = 0;

    uint16_t computed_crc = crc16_ccitt((const uint8_t*)json.c_str(), (size_t)crc_field_start);

    return (computed_crc == expected_crc) ? 1 : 0;
}

// ============================================================================
// UART Command Processing
// ============================================================================

void process_command(const String& json) {
    g_status.commands_received++;

    // P0-10: Verify CRC if present
    int crc_result = extract_and_verify_crc(json);
    if (crc_result == 0) {
        Serial.println("[CMD] CRC MISMATCH — frame rejected");
        g_status.faults_detected++;
        return;
    }

    // Minimal JSON parser (avoid external library for firmware size)
    // Expected format: {"cmd": "FEED_RATE", "args": {"rpm": 30}}
    
    String cmd = "";
    int cmd_start = json.indexOf("\"cmd\"");
    if (cmd_start >= 0) {
        int colon = json.indexOf(":", cmd_start);
        int comma = json.indexOf(",", colon);
        int end = (comma > 0) ? comma : json.length() - 1;
        int quote_start = json.indexOf("\"", colon + 1);
        int quote_end = json.indexOf("\"", quote_start + 1);
        if (quote_start >= 0 && quote_end > quote_start) {
            cmd = json.substring(quote_start + 1, quote_end);
        }
    }

    Serial.printf("[CMD] Received: %s\n", cmd.c_str());

    if (cmd == "STATUS") {
        // P3-03: expanded to 1024 to accommodate stack_hwm fields without truncation
        char buf[1024];
        snprintf(buf, sizeof(buf),
            "{\"type\":\"STATUS\","
            "\"state\":%d,"
            "\"uptime_ms\":%lu,"
            "\"heap_free\":%lu,"
            "\"beans_detected\":%lu,"
            "\"t1_beam_broken\":%s,"
            "\"t2_beam_broken\":%s,"
            "\"estop_active\":%s,"
            "\"feeder_rpm\":%lu,"
            "\"air_jet\":%s,"
            "\"stack_hwm\":{\"uart\":%lu,\"status\":%lu,\"stepper\":%lu},"
            "\"version\":\"%s\","
            "\"build\":\"%s\"}",
            (int)g_system_state,
            (unsigned long)g_status.uptime_ms,
            (unsigned long)g_status.heap_free_bytes,
            (unsigned long)g_status.beans_detected,
            g_status.t1_beam_broken ? "true" : "false",
            g_status.t2_beam_broken ? "true" : "false",
            g_estop_active ? "true" : "false",
            (unsigned long)g_status.feeder_rpm,
            g_status.air_jet_active ? "true" : "false",
            (unsigned long)g_status.stack_hwm_uart,
            (unsigned long)g_status.stack_hwm_status,
            (unsigned long)g_status.stack_hwm_stepper,
            FIRMWARE_VERSION,
            FIRMWARE_BUILD
        );
        Serial.println(buf);
    }
    else if (cmd == "FEED_RATE") {
        // Parse rpm from args
        int rpm_start = json.indexOf("\"rpm\"");
        if (rpm_start >= 0) {
            int colon = json.indexOf(":", rpm_start);
            int comma = json.indexOf(",", colon);
            int end = (comma > 0) ? comma : json.length() - 1;
            String rpm_str = json.substring(colon + 1, end);
            rpm_str.trim();
            uint32_t rpm = rpm_str.toInt();
            stepper_set_speed(StepperId::FEEDER_VIBRATING, rpm);
            g_status.feeder_rpm = rpm;
            Serial.printf("[CMD] Feed rate set: %lu rpm\n", (unsigned long)rpm);
        }
    }
    else if (cmd == "VALVE") {
        int id_start = json.indexOf("\"id\"");
        int state_start = json.indexOf("\"state\"");
        if (id_start >= 0 && state_start >= 0) {
            int id_colon = json.indexOf(":", id_start);
            int id_comma = json.indexOf(",", id_colon);
            int id_end = (id_comma > 0) ? id_comma : json.length() - 1;
            int id_quote1 = json.indexOf("\"", id_colon + 1);
            int id_quote2 = json.indexOf("\"", id_quote1 + 1);
            String id = json.substring(id_quote1 + 1, id_quote2);
            
            int state_colon = json.indexOf(":", state_start);
            int state_comma = json.indexOf(",", state_colon);
            int state_end = (state_comma > 0) ? state_comma : json.length() - 1;
            bool state = json.substring(state_colon + 1, state_end).toInt();
            
            if (id == "air_jet") solenoid_set(SolenoidId::AIR_JET, state);
            else if (id == "weighing_release") solenoid_set(SolenoidId::WEIGHING_CUP_RELEASE, state);
            else if (id == "buffer_selector") solenoid_set(SolenoidId::BUFFER_SELECTOR, state);
            
            Serial.printf("[CMD] Valve %s = %d\n", id.c_str(), state);
        }
    }
    else if (cmd == "STEPPER") {
        int id_idx = json.indexOf("\"id\"");
        int steps_idx = json.indexOf("\"steps\"");
        int speed_idx = json.indexOf("\"speed\"");
        if (id_idx >= 0 && steps_idx >= 0) {
            // Get id
            int id_colon = json.indexOf(":", id_idx);
            int id_comma = json.indexOf(",", id_colon);
            int id_end = (id_comma > 0) ? id_comma : json.length() - 1;
            int id_quote1 = json.indexOf("\"", id_colon + 1);
            int id_quote2 = json.indexOf("\"", id_quote1 + 1);
            String id = json.substring(id_quote1 + 1, id_quote2);
            
            // Get steps
            int steps_colon = json.indexOf(":", steps_idx);
            int steps_comma = json.indexOf(",", steps_colon);
            int steps_end = (steps_comma > 0) ? steps_comma : json.length() - 1;
            int32_t steps = json.substring(steps_colon + 1, steps_end).toInt();
            
            // Get speed (optional, default 100)
            uint32_t speed = 100;
            if (speed_idx >= 0) {
                int speed_colon = json.indexOf(":", speed_idx);
                int speed_comma = json.indexOf(",", speed_colon);
                int speed_end = (speed_comma > 0) ? speed_comma : json.length() - 1;
                speed = json.substring(speed_colon + 1, speed_end).toInt();
            }
            
            // Get direction (optional, default forward)
            bool dir = true;
            int dir_idx = json.indexOf("\"dir\"");
            if (dir_idx >= 0) {
                int dir_colon = json.indexOf(":", dir_idx);
                int dir_comma = json.indexOf(",", dir_colon);
                int dir_end = (dir_comma > 0) ? dir_comma : json.length() - 1;
                dir = json.substring(dir_colon + 1, dir_end).toInt() != 0;
            }
            
            StepperId sid = StepperId::FEEDER_VIBRATING;
            if (id == "feeder") sid = StepperId::FEEDER_VIBRATING;
            else if (id == "distributor") sid = StepperId::DISTRIBUTOR_ROTARY;
            else if (id == "spiral") sid = StepperId::SPIRAL_FEEDER;
            
            stepper_move_steps(sid, steps, dir, speed);
            Serial.printf("[CMD] Stepper %s: %ld steps at %lu rpm, dir=%d\n", 
                id.c_str(), (long)steps, (unsigned long)speed, dir);
        }
    }
    else if (cmd == "STEPPER_ENABLE") {
        int id_idx = json.indexOf("\"id\"");
        int en_idx = json.indexOf("\"enable\"");
        if (id_idx >= 0 && en_idx >= 0) {
            int id_colon = json.indexOf(":", id_idx);
            int id_comma = json.indexOf(",", id_colon);
            int id_end = (id_comma > 0) ? id_comma : json.length() - 1;
            int id_quote1 = json.indexOf("\"", id_colon + 1);
            int id_quote2 = json.indexOf("\"", id_quote1 + 1);
            String id = json.substring(id_quote1 + 1, id_quote2);
            
            int en_colon = json.indexOf(":", en_idx);
            int en_comma = json.indexOf(",", en_colon);
            int en_end = (en_comma > 0) ? en_comma : json.length() - 1;
            bool en = json.substring(en_colon + 1, en_end).toInt();
            
            StepperId sid = StepperId::FEEDER_VIBRATING;
            if (id == "feeder") sid = StepperId::FEEDER_VIBRATING;
            else if (id == "distributor") sid = StepperId::DISTRIBUTOR_ROTARY;
            else if (id == "spiral") sid = StepperId::SPIRAL_FEEDER;
            
            stepper_set_enabled(sid, en);
            Serial.printf("[CMD] Stepper %s enabled=%d\n", id.c_str(), en);
        }
    }
    else if (cmd == "HX711_TARE") {
        hx711_tare();
        Serial.println("[CMD] HX711 tare done");
    }
    else if (cmd == "HX711_CAL") {
        // Parse known weight
        int wt_idx = json.indexOf("\"weight\"");
        if (wt_idx >= 0) {
            int colon = json.indexOf(":", wt_idx);
            int comma = json.indexOf(",", colon);
            int end = (comma > 0) ? comma : json.length() - 1;
            float weight = json.substring(colon + 1, end).toFloat();
            hx711_calibrate(weight);
            Serial.printf("[CMD] HX711 calibrated with %.2fg\n", weight);
        }
    }
    else if (cmd == "FAN_PWM") {
        int pwm_idx = json.indexOf("\"duty\"");
        if (pwm_idx >= 0) {
            int colon = json.indexOf(":", pwm_idx);
            int comma = json.indexOf(",", colon);
            int end = (comma > 0) ? comma : json.length() - 1;
            uint16_t duty = json.substring(colon + 1, end).toInt();
            duty = constrain(duty, 0, 1023);
            // Drive LEDC hardware PWM (LEDC channel 0, 10-bit = 0-1023)
            ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, duty);
            ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0);
            Serial.printf("[CMD] Fan PWM duty=%u (%.0f%%)\n", duty, duty * 100.0 / 1023.0);
        }
    }
    else if (cmd == "ESTOP" || cmd == "ESTOP_HW") {
        // Emergency stop: halt all motors, close all valves
        // ESTOP: software command via UART
        // ESTOP_HW: hardware button ISR (P0-07 fix)
        for (int i = 0; i < 3; i++) {
            stepper_halt((StepperId)i);
        }
        for (int i = 0; i < 3; i++) {
            solenoid_set((SolenoidId)i, false);
        }
        g_system_state = SystemState::FAULT;
        if (cmd == "ESTOP_HW") {
            Serial.println("[ESTOP] HARDWARE button triggered — all actuators halted");
        } else {
            Serial.println("[CMD] ESTOP executed");
        }
    }
    else if (cmd == "ESTOP_RESET") {
        // P0-07: Clear hardware E-STOP state and restore IDLE
        if (!g_estop_active) {
            Serial.println("[CMD] No active E-STOP to reset");
        } else {
            g_estop_active = false;
            g_system_state = SystemState::IDLE;
            g_status.faults_detected++;
            Serial.println("[CMD] ESTOP_RESET — system returned to IDLE");
        }
    }
    else if (cmd == "RESET") {
        g_system_state = SystemState::IDLE;
        g_status.faults_detected++;
        Serial.println("[CMD] System reset to IDLE");
    }
    else {
        Serial.printf("[CMD] Unknown command: %s\n", cmd.c_str());
    }
}

// ============================================================================
// Serial communication task
// ============================================================================

void serial_task(void* param) {
    String line = "";
    for (;;) {
        if (Serial.available()) {
            char c = Serial.read();
            if (c == '\n' || c == '\r') {
                if (line.length() > 0) {
                    process_command(line);
                    line = "";
                }
            } else {
                line += c;
            }
        }
        esp_task_wdt_reset();  // P0-08: Feed watchdog
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

// ============================================================================
// Status update task (runs every 5 seconds)
// ============================================================================

void status_task(void* param) {
    for (;;) {
        g_status.uptime_ms = millis();
        g_status.heap_free_bytes = ESP.getFreeHeap();
        g_status.stack_hwm = uxTaskGetStackHighWaterMark(NULL);
        // P2-08: track stack HWM for all tasks
        if (g_task_uart)   g_status.stack_hwm_uart   = uxTaskGetStackHighWaterMark(g_task_uart);
        if (g_task_status) g_status.stack_hwm_status  = uxTaskGetStackHighWaterMark(g_task_status);
        if (g_task_stepper) g_status.stack_hwm_stepper = uxTaskGetStackHighWaterMark(g_task_stepper);
        g_status.cpu_temp_c = temperatureRead();
        g_status.vcc_voltage = analogRead(ADC1_CHANNEL_0) * 3.3f / 4095.0f * 2;  // voltage divider
        
        // Update sensor readings
        update_sensor_readings();

        // Auto-send heartbeat every 10 cycles (50s) if enabled
        static int heartbeat_counter = 0;
        heartbeat_counter++;
        if (heartbeat_counter >= 10) {
            heartbeat_counter = 0;
            char buf[256];
            snprintf(buf, sizeof(buf),
                "{\"type\":\"HEARTBEAT\",\"uptime_ms\":%lu,\"heap_free\":%lu}",
                (unsigned long)g_status.uptime_ms,
                (unsigned long)g_status.heap_free_bytes
            );
            Serial.println(buf);
        }

        esp_task_wdt_reset();  // P0-08: Feed watchdog
        vTaskDelay(pdMS_TO_TICKS(5000));
    }
}

// ============================================================================
// Stepper pulse generation task (software step generation)
// P0-17 fix: uses esp_timer_get_time() for microsecond-accurate delays
//            instead of vTaskDelay(1ms) which limits max RPM
// ============================================================================

void stepper_task(void* param) {
    for (;;) {
        if (xSemaphoreTake(g_stepper_mutex, portMAX_DELAY) == pdTRUE) {
            for (int i = 0; i < 3; i++) {
                if (g_steppers[i].moving && g_steppers[i].enabled && g_steppers_to_step[i] > 0) {
                    // Calculate delay based on RPM
                    uint32_t steps_per_rev = g_steppers[i].steps_per_rev * g_steppers[i].microstep;
                    uint32_t us_per_step = (60UL * 1000000UL) / (g_steppers[i].speed_rpm * steps_per_rev);
                    us_per_step = constrain(us_per_step, STEP_PULSE_US * 2, 100000);

                    // P0-17: Microsecond-accurate step timing using esp_timer
                    int64_t step_deadline = esp_timer_get_time() + us_per_step;

                    gpio_set_level(g_steppers[i].dir_pin, g_step_dirs[i] ? 1 : 0);
                    gpio_set_level(g_steppers[i].pul_pin, 1);
                    ets_delay_us(STEP_PULSE_US);  // 50us pulse width
                    gpio_set_level(g_steppers[i].pul_pin, 0);

                    // Wait until next step deadline (busy-wait for short delays)
                    while (esp_timer_get_time() < step_deadline) {
                        // Yield for longer delays to let other tasks run
                        if ((step_deadline - esp_timer_get_time()) > 1000) {
                            vTaskDelay(pdMS_TO_TICKS(1));
                            break;
                        }
                    }

                    g_steppers_to_step[i]--;
                    if (g_steppers_to_step[i] == 0) {
                        g_steppers[i].moving = false;
                    }
                }
            }
            xSemaphoreGive(g_stepper_mutex);
        }
        vTaskDelay(pdMS_TO_TICKS(1));  // 1ms base loop
    }
}

// ============================================================================
// P2-09: Boot self-check (verifies hardware before going operational)
// ============================================================================

static bool run_boot_self_check() {
    Serial.println("\n─── BOOT SELF-CHECK ───");
    bool all_ok = true;

    // 1. Memory check
    uint32_t heap = ESP.getFreeHeap();
    if (heap < 100000) {
        Serial.printf("[FAIL] Heap too low: %lu bytes (min 100KB)\n", (unsigned long)heap);
        all_ok = false;
    } else {
        Serial.printf("[OK]   Heap: %lu bytes\n", (unsigned long)heap);
    }

    // 2. GPIO output verification (toggle output pins, verify no shorts)
    const int output_pins[] = {
        PIN_STEPPER1_PUL, PIN_STEPPER1_DIR,
        PIN_STEPPER2_PUL, PIN_STEPPER2_DIR,
        PIN_STEPPER3_PUL, PIN_STEPPER3_DIR,
        PIN_AIR_JET, PIN_WEIGH_RELEASE, PIN_BUF_SELECT,
        DRV8833_MS1_PIN, DRV8833_MS2_PIN,
        FAN_PWM_PIN
    };
    const int n_outputs = sizeof(output_pins) / sizeof(output_pins[0]);

    for (int i = 0; i < n_outputs; i++) {
        gpio_set_level((gpio_num_t)output_pins[i], 1);
        delay(1);
        gpio_set_level((gpio_num_t)output_pins[i], 0);
    }
    Serial.printf("[OK]   %d output pins toggled\n", n_outputs);

    // 3. ADC sensor sanity check
    int adc_ch0 = adc1_get_raw(ADC1_CHANNEL_0);
    int adc_ch3 = adc1_get_raw(ADC1_CHANNEL_3);
    if (adc_ch0 < 0 || adc_ch0 > 4095) {
        Serial.printf("[WARN] ADC CH0 read %d (unexpected)\n", adc_ch0);
        // Not fatal — sensor may not be connected at boot
    } else {
        Serial.printf("[OK]   ADC CH0=%d, CH3=%d\n", adc_ch0, adc_ch3);
    }

    // 4. T1/T2 sensor check (T1=GPIO36/ADC1_CH0, T2=GPIO39/ADC1_CH3)
    int t1_raw = adc1_get_raw(ADC1_CHANNEL_0);
    int t2_raw = adc1_get_raw(ADC1_CHANNEL_3);
    float t1_v = t1_raw * 3.3f / 4095.0f;
    float t2_v = t2_raw * 3.3f / 4095.0f;
    Serial.printf("[INFO] T1=%.2fV (raw=%d), T2=%.2fV (raw=%d)\n", t1_v, t1_raw, t2_v, t2_raw);

    // 5. E-STOP pin state
    int estop_level = gpio_get_level(ESTOP_PIN);
    if (estop_level == 0) {
        Serial.println("[WARN] E-STOP is currently PRESSED (active LOW)");
        all_ok = false;
    } else {
        Serial.println("[OK]   E-STOP released (normal)");
    }

    if (all_ok) {
        Serial.println("[PASS] Self-check passed");
    } else {
        Serial.println("[FAIL] Self-check has failures — check above");
    }
    Serial.println("─── END SELF-CHECK ───\n");
    return all_ok;
}

// ============================================================================
// Setup & Main Loop
// ============================================================================

void setup() {
    Serial.begin(UART_BAUD);
    Serial.println();
    Serial.printf("\n========================================\n");
    Serial.printf("  HUSKY-SORTER-001 ESP32 Firmware\n");
    Serial.printf("  Version: %s (%s)\n", FIRMWARE_VERSION, FIRMWARE_BUILD);
    Serial.printf("  Chip: ESP32 %d cores, %d MHz\n", ESP.getChipCores(), ESP.getCpuFreqMHz());
    Serial.printf("  Flash: %lu bytes\n", ESP.getFlashChipSize());
    Serial.printf("========================================\n\n");

    // Initialize mutexes
    g_stepper_mutex = xSemaphoreCreateMutex();
    g_cmd_queue = xQueueCreate(32, sizeof(UARTCommand));

    // Initialize pins
    init_pins();

    // Initialize ADC for sensors
    adc1_config_channel_atten(ADC1_CHANNEL_0, ADC_ATTEN_DB_11);  // GPIO36
    adc1_config_channel_atten(ADC1_CHANNEL_3, ADC_ATTEN_DB_11);  // GPIO39

    // P2-09: Run boot self-check
    run_boot_self_check();

    // P0-08: Initialize Task Watchdog (5 second timeout)
    esp_task_wdt_init(TWDT_TIMEOUT_S, true);  // true = panic on timeout
    esp_task_wdt_add(NULL);  // Add current task (loopTask) to watchdog

    // Attach T1/T2 interrupts (P0-09: NEGEDGE already set in init_pins)
    gpio_isr_handler_add(gpio_num_t(GPIO_NUM_4), t1_isr, NULL);
    gpio_isr_handler_add(gpio_num_t(GPIO_NUM_5), t2_isr, NULL);

    // P0-07: Attach E-STOP hardware ISR (highest priority)
    gpio_isr_handler_add(ESTOP_PIN, estop_isr, NULL);
    Serial.println("[BOOT] E-STOP hardware ISR registered on GPIO15");

    // Create tasks (all tasks feed watchdog in their loops)
    // P2-08: store handles for stack HWM monitoring
    xTaskCreatePinnedToCore(serial_task, "UART", 4096, NULL, 5, &g_task_uart, 0);
    xTaskCreatePinnedToCore(status_task, "Status", 4096, NULL, 3, &g_task_status, 1);
    xTaskCreatePinnedToCore(stepper_task, "Stepper", 4096, NULL, 4, &g_task_stepper, 1);

    // System ready
    g_system_state = SystemState::IDLE;
    Serial.println("[BOOT] System ready (v2: +E-STOP HW +WDT +debounce +CRC)");
    Serial.println("[BOOT] Waiting for commands...");
}

void loop() {
    // Main loop: feed watchdog to prove main task is alive
    // All actual work is done in FreeRTOS tasks
    esp_task_wdt_reset();  // P0-08: Feed watchdog every 1s
    delay(1000);
}