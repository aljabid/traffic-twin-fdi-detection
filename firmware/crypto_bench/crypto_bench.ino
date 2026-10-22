#include <uECC.h>
#include <Crypto.h>
#include <SHA256.h>

const uECC_Curve_t* curve = uECC_secp256r1();
uint8_t privateKey[32], publicKey[64], digest[32], signature[64], message[64];

static int rng(uint8_t* dest, unsigned size) {
  while (size--) { uint8_t v = 0; for (int i = 0; i < 8; i++) v = (v << 1) ^ (analogRead(A5) & 1) ^ (micros() & 1) ^ random(2); *dest++ = v; }
  return 1;
}

void report(const char* op, int runs, unsigned long total, unsigned long mn, unsigned long mx) {
  Serial.print("R,"); Serial.print(op); Serial.print(','); Serial.print(runs); Serial.print(',');
  Serial.print(total / 1000.0 / runs, 3); Serial.print(','); Serial.print(mn / 1000.0, 3); Serial.print(','); Serial.println(mx / 1000.0, 3);
}

template <typename F> void bench(const char* op, int runs, F f) {
  unsigned long total = 0, mn = 0xFFFFFFFF, mx = 0;
  for (int i = 0; i < runs; i++) {
    unsigned long t = micros(); f(); unsigned long d = micros() - t;
    total += d; if (d < mn) mn = d; if (d > mx) mx = d;
  }
  report(op, runs, total, mn, mx);
}

void setup() {
  Serial.begin(115200);
  randomSeed(analogRead(A5));
  uECC_set_rng(&rng);
  for (int i = 0; i < 64; i++) message[i] = i * 7 + 3;
  Serial.println("# crypto bench start");
  bench("sha256_64B", 1000, [] { SHA256 h; h.update(message, 64); h.finalize(digest, 32); });
  bench("hmac_sha256_64B", 1000, [] { SHA256 h; uint8_t key[32] = {1}; h.resetHMAC(key, 32); h.update(message, 64); h.finalizeHMAC(key, 32, digest, 32); });
  bench("ecdsa_p256_keygen", 5, [] { uECC_make_key(publicKey, privateKey, curve); });
  { SHA256 h; h.update(message, 64); h.finalize(digest, 32); }
  bench("ecdsa_p256_sign", 20, [] { uECC_sign(privateKey, digest, 32, signature, curve); });
  int ok = 0;
  bench("ecdsa_p256_verify", 20, [&ok] { ok += uECC_verify(publicKey, digest, 32, signature, curve); });
  Serial.print("# verify ok "); Serial.print(ok); Serial.println("/20");
  Serial.println("# crypto bench done");
}

void loop() {}
