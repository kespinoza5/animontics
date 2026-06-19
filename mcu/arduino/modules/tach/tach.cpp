#include "tach.h"

// Module-global interrupt bank: attachInterrupt() needs a plain function pointer,
// so each FG pin is bound to one fixed counter + ISR. Slots are handed out across
// all tach instances (TACH_MAX total).
static volatile uint32_t s_counts[Tach::TACH_MAX] = {0};
static uint8_t s_next_slot = 0;

static void isr0() { s_counts[0]++; }
static void isr1() { s_counts[1]++; }
static void isr2() { s_counts[2]++; }
static void isr3() { s_counts[3]++; }
static void isr4() { s_counts[4]++; }
static void isr5() { s_counts[5]++; }
static void (*const s_isrs[Tach::TACH_MAX])() = {isr0, isr1, isr2, isr3, isr4, isr5};

void Tach::setup() {
  for (uint8_t i = 0; i < _count; ++i) {
    uint8_t slot = (s_next_slot < TACH_MAX) ? s_next_slot++ : (TACH_MAX - 1);
    _slot[i] = slot;
    noInterrupts();
    s_counts[slot] = 0;
    interrupts();
    pinMode(_pins[i], INPUT_PULLUP);                       // FG is open-collector
    attachInterrupt(digitalPinToInterrupt(_pins[i]), s_isrs[slot], FALLING);
  }
  _last_ms = millis();
}

void Tach::read(int16_t *out, unsigned long now) {
  unsigned long dt = now - _last_ms;
  _last_ms = now;
  for (uint8_t i = 0; i < _count; ++i) {
    uint8_t slot = _slot[i];
    noInterrupts();
    uint32_t edges = s_counts[slot];
    s_counts[slot] = 0;
    interrupts();
    // rpm = edges * 60000ms / (pulses_per_rev * dt_ms)
    uint32_t rpm = (dt > 0) ? (edges * 60000UL) / ((uint32_t)_ppr * dt) : 0;
    out[i] = (rpm > 32767UL) ? 32767 : (int16_t)rpm;
  }
}
