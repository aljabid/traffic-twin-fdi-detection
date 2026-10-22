#include <esp_random.h>
#include "randombytes.h"

int randombytes(uint8_t *output, size_t n) {
    esp_fill_random(output, n);
    return 0;
}
