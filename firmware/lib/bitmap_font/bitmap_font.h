#pragma once
// 1비트 서브셋 비트맵 폰트 — 코드포인트 조회와 글자 한 개 그리기(낮은 계층).
// v1 KoreanFont.h 의 ngIdx(산술 인덱스) + ngDrawChar 를 대체한다. 줄 조판(ngPrintLine/ngPrint 에
// 해당하는 진행·줄바꿈·정렬)은 여기 두지 않는다 — dh-04 Task 4(renderLayout 이식) 몫이다.
//
// 자산: firmware/src/fonts/<name>.bin(+.json) 을 빌드 직전 tools/embed_fonts.py 가 lib/font_data/ 에
// C 배열로 생성한다(dh-04 plan D2). 인스턴스(kNanum20Regular 등)는 "font_data.h" 에 선언된다.
//
// 저장 형식
//   - codepoints[count]: 오름차순. 전체 폰트는 lora_proto/lora_proto/charset.txt 순서 그대로다.
//     v1 은 ASCII+한글 전체라 cp 에서 인덱스를 산술로 구했지만, 서브셋은 빠진 음절·목록 밖 기호가
//     섞여 있어 산술식이 통하지 않는다 → 이진탐색(최대 12회 비교, 2,459자).
//   - bitmaps: 글리프마다 같은 셀(cellW×cellH, 행 우선, 행당 bytesPerRow 바이트, MSB 가 왼쪽).
//     셀 크기가 모두 같아 글리프 i 는 bitmaps + i * cellH * bytesPerRow — 오프셋 표가 필요 없다.
//   - advances[count]: 글자마다 다음 펜 위치까지의 폭(px, 비례폭).
//
// 좌표 규약: (x, baselineY) 는 **펜 원점**(베이스라인 위 왼쪽)이다. 셀 왼쪽 위 = (x - originX,
// baselineY - baseline). 크기가 다른 글자(예: 32px 호수 + 16px "호")를 베이스라인으로 맞추기 위함이다.
//
// 데이터는 const 배열이라 ESP32 에서는 플래시(메모리 매핑)에 놓이고 직접 읽을 수 있다 —
// AVR 식 pgm_read_byte 가 필요 없다.
#include <cstdint>

class Adafruit_GFX;

struct BitmapFont {
  const uint16_t* codepoints;
  const uint8_t* advances;
  const uint8_t* bitmaps;
  uint16_t count;
  uint8_t cellW;
  uint8_t cellH;
  uint8_t bytesPerRow;
  uint8_t baseline;  // 셀 윗변에서 베이스라인까지(px)
  int8_t originX;    // 셀 왼쪽 변에서 펜 원점까지(px). 음수면 셀이 펜 원점 오른쪽에서 시작
};

// 글리프 인덱스. 없으면 -1.
int32_t bfFindGlyph(const BitmapFont& f, uint32_t cp);

inline uint16_t bfBytesPerGlyph(const BitmapFont& f) {
  return (uint16_t)(f.cellH * f.bytesPerRow);
}

// idx 는 bfFindGlyph 가 돌려준 0 이상 값이어야 한다.
inline const uint8_t* bfGlyphBitmap(const BitmapFont& f, int32_t idx) {
  return f.bitmaps + (uint32_t)idx * bfBytesPerGlyph(f);
}

// 잉크 비트만 color 로 찍는다(바탕은 건드리지 않음 — 반전면 위 흰 글자도 같은 함수).
// 반환: 진행폭(px). 글리프가 없으면 아무것도 그리지 않고 0 — 대체 글자(□ 등) 정책은 호출부가 정한다.
int16_t bfDrawGlyph(Adafruit_GFX& gfx, const BitmapFont& f, uint32_t cp, int16_t x, int16_t baselineY,
                    uint16_t color);
