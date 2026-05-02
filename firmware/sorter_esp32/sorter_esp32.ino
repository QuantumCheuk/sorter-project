/**
 * HUSKY-SORTER-001 ESP32 Firmware
 * 
 * Main controller for sensor reading, motor control, and Pi communication.
 * 
 * Hardware: ESP32 DevKit v1 (30-pin)
 * 
 * Pin Assignment (v1.0):
 *   GPIO4  (INPUT)  - T1 sensor (top bean detector)
 *   GPIO5  (INPUT)  - T2 sensor (bottom bean detector)  
 *   GPIO18 (OUTPUT) - Stepper1 PUL (vibrating feeder)
 *   GPIO19 (OUTPUT) - Stepper1 DIR
 *   GPIO21 (OUTPUT) - Stepper2 PUL (rotary distributor)
 *   GPIO22 (OUTPUT) - Stepper2 DIR
 *   GPIO16 (OUTPUT) - Air jet solenoid valve
 *   GPIO17 (OUTPUT) - Weighing cup release solenoid
 *   GPIO25 (OUTPUT) - Buffer selector valve
 *   GPIO26 (OUTPUT) - Stepper3 PUL (spiral feeder)
 *   GPIO27 (OUTPUT) - Stepper3 DIR
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
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>
#include <HardwareSerial.h>
#include <vector>

// ============================================================================
// Configuration
// ============================================================================

#define FIRMWARE_VERSION "1.0.0"
#define FIRMWARE_BUILD "2026-05-03"

// UART to Pi
#define UART_TX_PIN 1
#define UART_RX_PIN 3
#define UART_BAUD 115200

// Stepper pulse timing (microseconds)
#define STEP_PULSE_US 50

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

// ============================================================================
// Pin Initialization
// ============================================================================

void init_pins() {
    // T1/T2 sensor inputs (analog ADC, infrared beam broken = voltage drop)
    gpio_config_t t1_conf = {
        .pin_bit_mask = (1ULL << GPIO_NUM_4),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_ANYEDGE  // trigger on any change
    };
    gpio_config(&t1_conf);

    gpio_config_t t2_conf = {
        .pin_bit_mask = (1ULL << GPIO_NUM_5),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_ANYEDGE
    };
    gpio_config(&t2_conf);

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

    // Fan PWM (GPIO13 -> ledc channel 0, timer 0)
    gpio_reset_pin(gpio_num_t(GPIO_NUM_13));
    gpio_set_direction(gpio_num_t(GPIO_NUM_13), GPIO_MODE_OUTPUT);

    // ADC for sensors
    adc1_config_width(ADC_WIDTH_BIT_12);

    Serial.println("[INIT] GPIO pins initialized");
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
// ============================================================================

void solenoid_set(SolenoidId id, bool on, uint32_t pulse_ms = 0) {
    int idx = static_cast<int>(id);
    gpio_set_level(g_solenoids[idx].pin, on ? 1 : 0);
    g_solenoids[idx].state = on;

    if (on && pulse_ms > 0) {
        // Auto-off after pulse duration
        // Use a simple delay for pulse mode (non-blocking would need timer)
        vTaskDelay(pdMS_TO_TICKS(pulse_ms));
        gpio_set_level(g_solenoids[idx].pin, 0);
        g_solenoids[idx].state = false;
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
    // T1/T2 are infrared break-beam sensors
    // When bean breaks beam, voltage drops (analog reading changes)
    // Calibration: break = reading < threshold, clear = reading > threshold
    const int T1_THRESHOLD = 2048;  // mid-range of 0-4095
    const int T2_THRESHOLD = 2048;
    
    int t1_raw = adc1_get_raw(ADC1_CHANNEL_0);  // GPIO36 = ADC1_CH0
    int t2_raw = adc1_get_raw(ADC1_CHANNEL_3);  // GPIO39 = ADC1_CH3
    
    g_status.t1_beam_voltage = t1_raw * 3.3f / 4095.0f;
    g_status.t2_beam_voltage = t2_raw * 3.3f / 4095.0f;
    g_status.t1_beam_broken = (t1_raw < T1_THRESHOLD);
    g_status.t2_beam_broken = (t2_raw < T2_THRESHOLD);
}

bool IRAM_ATTR t1_isr() {
    BaseType_t high_task_woken = pdFALSE;
    uint32_t now = millis();
    xQueueSendFromISR(g_cmd_queue, &(UARTCommand{"T1_TRIGGER", String(now)}), &high_task_woken);
    g_status.beans_detected++;
    return high_task_woken == pdTRUE ? true : false;
}

bool IRAM_ATTR t2_isr() {
    BaseType_t high_task_woken = pdFALSE;
    uint32_t now = millis();
    xQueueSendFromISR(g_cmd_queue, &(UARTCommand{"T2_TRIGGER", String(now)}), &high_task_woken);
    return high_task_woken == pdTRUE ? true : false;
}

// ============================================================================
// UART Command Processing
// ============================================================================

void process_command(const String& json) {
    g_status.commands_received++;

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
        // Send full status
        char buf[512];
        snprintf(buf, sizeof(buf),
            "{\"type\":\"STATUS\","
            "\"state\":%d,"
            "\"uptime_ms\":%lu,"
            "\"heap_free\":%lu,"
            "\"beans_detected\":%lu,"
            "\"t1_beam_broken\":%s,"
            "\"t2_beam_broken\":%s,"
            "\"feeder_rpm\":%lu,"
            "\"air_jet\":%s,"
            "\"version\":\"%s\"}",
            (int)g_system_state,
            (unsigned long)g_status.uptime_ms,
            (unsigned long)g_status.heap_free_bytes,
            (unsigned long)g_status.beans_detected,
            g_status.t1_beam_broken ? "true" : "false",
            g_status.t2_beam_broken ? "true" : "false",
            (unsigned long)g_status.feeder_rpm,
            g_status.air_jet_active ? "true" : "false",
            FIRMWARE_VERSION
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
            // 0-1023 range for ESP32 LEDC
            duty = constrain(duty, 0, 1023);
            // Simple PWM via GPIO toggle in software
            // For real implementation, use LEDC hardware peripheral
            // Here we just acknowledge the command
            Serial.printf("[CMD] Fan PWM duty=%u\n", duty);
        }
    }
    else if (cmd == "ESTOP") {
        // Emergency stop: halt all motors, close all valves
        for (int i = 0; i < 3; i++) {
            stepper_halt((StepperId)i);
        }
        for (int i = 0; i < 3; i++) {
            solenoid_set((SolenoidId)i, false);
        }
        g_system_state = SystemState::FAULT;
        Serial.println("[CMD] ESTOP executed");
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

        vTaskDelay(pdMS_TO_TICKS(5000));
    }
}

// ============================================================================
// Stepper pulse generation task (software step generation)
// ============================================================================

void stepper_task(void* param) {
    for (;;) {
        if (xSemaphoreTake(g_stepper_mutex, portMAX_DELAY) == pdTRUE) {
            for (int i = 0; i < 3; i++) {
                if (g_steppers[i].moving && g_steppers[i].enabled && g_steppers_to_step[i] > 0) {
                    // Calculate delay based on RPM
                    // steps_per_rev * microstep * 60 / rpm = us per revolution
                    uint32_t steps_per_rev = g_steppers[i].steps_per_rev * g_steppers[i].microstep;
                    uint32_t us_per_step = (steps_per_rev * 1000000UL) / (g_steppers[i].speed_rpm * 60);
                    us_per_step = constrain(us_per_step, STEP_PULSE_US + 10, 100000);  // clamp 50us to 100ms

                    gpio_set_level(g_steppers[i].dir_pin, g_step_dirs[i] ? 1 : 0);
                    gpio_set_level(g_steppers[i].pul_pin, 1);
                    delayMicroseconds(STEP_PULSE_US);
                    gpio_set_level(g_steppers[i].pul_pin, 0);
                    
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

    // Attach T1/T2 interrupts
    gpio_set_intr_type(gpio_num_t(GPIO_NUM_4), GPIO_INTR_ANYEDGE);
    gpio_isr_register(t1_isr, NULL, ESP_INTR_FLAG_IRAM);
    gpio_intr_enable(gpio_num_t(GPIO_NUM_4));

    gpio_set_intr_type(gpio_num_t(GPIO_NUM_5), GPIO_INTR_ANYEDGE);
    gpio_isr_register(t2_isr, NULL, ESP_INTR_FLAG_IRAM);
    gpio_intr_enable(gpio_num_t(GPIO_NUM_5));

    // Create tasks
    xTaskCreatePinnedToCore(serial_task, "UART", 4096, NULL, 5, NULL, 0);
    xTaskCreatePinnedToCore(status_task, "Status", 4096, NULL, 3, NULL, 1);
    xTaskCreatePinnedToCore(stepper_task, "Stepper", 4096, NULL, 4, NULL, 1);

    // System ready
    g_system_state = SystemState::IDLE;
    Serial.println("[BOOT] System ready, waiting for commands...");
    Serial.println("[BOOT] Send {\"cmd\":\"STATUS\"} to get current status");
}

void loop() {
    // Main loop does nothing - all work is in tasks
    // This ensures RTOS task scheduling
    delay(1000);
}