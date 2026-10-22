#include <mbedtls/sha256.h>
#include <mbedtls/md.h>
#include <mbedtls/ecdsa.h>
#include <esp_random.h>
#include <esp_heap_caps.h>
extern "C" {
#include "src/mlkem768/api.h"
#include "src/mldsa65/api.h"
}

const uint32_t TASK_STACK = 104 * 1024;
const int DSA_SIGNS = 1000;
uint8_t message[64], digest[32], hmacKey[32];
SemaphoreHandle_t groupDone;
uint32_t peakStack;
uint32_t* cycleTimes;
StaticTask_t taskBuffer;
StackType_t* taskStack;

void out(const char* fmt, ...) {
  char buf[192];
  va_list args;
  va_start(args, fmt);
  vsnprintf(buf, sizeof(buf), fmt, args);
  va_end(args);
  Serial.print(buf);
}

static int rng(void*, unsigned char* out, size_t n) { esp_fill_random(out, n); return 0; }

static int cmp(const void* a, const void* b) {
  uint32_t x = *(const uint32_t*)a, y = *(const uint32_t*)b;
  return (x > y) - (x < y);
}

void report(const char* op, int runs) {
  uint64_t total = 0;
  for (int i = 0; i < runs; i++) total += cycleTimes[i];
  qsort(cycleTimes, runs, sizeof(uint32_t), cmp);
  int p99 = (99 * (runs - 1) + 50) / 100;
  out("R,%s,%d,%lu,%lu,%lu,%lu,%lu\n", op, runs, (unsigned long)(total / runs), (unsigned long)cycleTimes[0],
      (unsigned long)cycleTimes[runs - 1], (unsigned long)cycleTimes[runs / 2], (unsigned long)cycleTimes[p99]);
}

template <typename F> void bench(const char* op, int runs, F f) {
  for (int i = 0; i < runs; i++) {
    uint32_t t = ESP.getCycleCount(); f(); cycleTimes[i] = ESP.getCycleCount() - t;
    if (i % 50 == 49) vTaskDelay(1);
  }
  report(op, runs);
}

void groupSymmetric() {
  bench("sha256_64B", 1000, [] { mbedtls_sha256(message, 64, digest, 0); });
  const mbedtls_md_info_t* md = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  bench("hmac_sha256_64B", 1000, [md] { mbedtls_md_hmac(md, hmacKey, 32, message, 64, digest); });
}

void groupEcdsa() {
  mbedtls_ecdsa_context ctx;
  mbedtls_ecdsa_init(&ctx);
  bench("ecdsa_p256_keygen", 20, [&ctx] { mbedtls_ecdsa_free(&ctx); mbedtls_ecdsa_init(&ctx);
                                           mbedtls_ecdsa_genkey(&ctx, MBEDTLS_ECP_DP_SECP256R1, rng, NULL); });
  mbedtls_sha256(message, 64, digest, 0);
  static uint8_t sig[MBEDTLS_ECDSA_MAX_LEN];
  static size_t sigLen;
  bench("ecdsa_p256_sign", 200, [&ctx] { mbedtls_ecdsa_write_signature(&ctx, MBEDTLS_MD_SHA256, digest, 32, sig,
                                                                       sizeof(sig), &sigLen, rng, NULL); });
  int ok = 0;
  bench("ecdsa_p256_verify", 200, [&ctx, &ok] { ok += mbedtls_ecdsa_read_signature(&ctx, digest, 32, sig, sigLen) == 0; });
  out("# ecdsa verify ok %d/200\n", ok);
  mbedtls_ecdsa_free(&ctx);
}

void groupMlKem() {
  static uint8_t pk[PQCLEAN_MLKEM768_CLEAN_CRYPTO_PUBLICKEYBYTES], sk[PQCLEAN_MLKEM768_CLEAN_CRYPTO_SECRETKEYBYTES],
      ct[PQCLEAN_MLKEM768_CLEAN_CRYPTO_CIPHERTEXTBYTES], ss1[32], ss2[32];
  bench("mlkem768_keygen", 1000, [] { PQCLEAN_MLKEM768_CLEAN_crypto_kem_keypair(pk, sk); });
  bench("mlkem768_encaps", 1000, [] { PQCLEAN_MLKEM768_CLEAN_crypto_kem_enc(ct, ss1, pk); });
  int ok = 0;
  bench("mlkem768_decaps", 1000, [&ok] { PQCLEAN_MLKEM768_CLEAN_crypto_kem_dec(ss2, ct, sk); ok += memcmp(ss1, ss2, 32) == 0; });
  out("# mlkem shared secret match %d/1000\n", ok);
}

void groupMlDsa() {
  static uint8_t pk[PQCLEAN_MLDSA65_CLEAN_CRYPTO_PUBLICKEYBYTES], sk[PQCLEAN_MLDSA65_CLEAN_CRYPTO_SECRETKEYBYTES],
      sig[PQCLEAN_MLDSA65_CLEAN_CRYPTO_BYTES];
  static size_t sigLen;
  bench("mldsa65_keygen", 100, [] { PQCLEAN_MLDSA65_CLEAN_crypto_sign_keypair(pk, sk); });

  bench("mldsa65_sign", DSA_SIGNS, [] { esp_fill_random(message, 64);
                                        PQCLEAN_MLDSA65_CLEAN_crypto_sign_signature(sig, &sigLen, message, 64, sk); });
  for (int i = 0; i < DSA_SIGNS; i++) out("S,%d,%lu\n", i, (unsigned long)cycleTimes[i]);
  int ok = 0;
  bench("mldsa65_verify", 1000, [&ok] { ok += PQCLEAN_MLDSA65_CLEAN_crypto_sign_verify(sig, sigLen, message, 64, pk) == 0; });
  out("# mldsa verify ok %d/1000\n", ok);
}

void (*currentGroup)();

void groupTask(void*) {
  currentGroup();
  peakStack = TASK_STACK - uxTaskGetStackHighWaterMark(NULL);
  xSemaphoreGive(groupDone);
  vTaskDelete(NULL);
}

void runGroup(const char* name, void (*g)()) {
  currentGroup = g;
  if (xTaskCreateStaticPinnedToCore(groupTask, name, TASK_STACK, NULL, 1, taskStack, &taskBuffer, 1) == NULL) {
    out("# %s: task create failed\n", name);
    return;
  }
  xSemaphoreTake(groupDone, portMAX_DELAY);
  delay(200);
  out("STACK,%s,%u\n", name, peakStack);
}

void setup() {
  Serial.begin(115200);
  delay(2000);
  groupDone = xSemaphoreCreateBinary();
  taskStack = (StackType_t*)heap_caps_malloc(TASK_STACK, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  cycleTimes = (uint32_t*)malloc(DSA_SIGNS * sizeof(uint32_t));
  for (int i = 0; i < 64; i++) message[i] = i * 7 + 3;
  for (int i = 0; i < 32; i++) hmacKey[i] = i + 1;
  out("# crypto bench start: %s rev %d, %u MHz, free heap %u, largest block %u\n", ESP.getChipModel(),
                ESP.getChipRevision(), getCpuFrequencyMhz(), ESP.getFreeHeap(),
                heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
  out("CLOCK,%u\n", getCpuFrequencyMhz());
  runGroup("symmetric", groupSymmetric);
  runGroup("ecdsa", groupEcdsa);
  runGroup("mlkem768", groupMlKem);
  runGroup("mldsa65", groupMlDsa);
  out("# min free heap %u\n", ESP.getMinFreeHeap());
  Serial.println("# crypto bench done");
}

void loop() { delay(1000); }
