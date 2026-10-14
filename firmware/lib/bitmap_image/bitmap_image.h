#pragma once
// 1비트 고정 문구 이미지(상태명·layout 8 제목·칩 글자) — 낮은 계층.
// bitmap_font.h 의 자매 자산이다: 폰트는 코드포인트별 글리프 조회가 필요한 가변 문자열용이고,
// 이미지는 RenderModel 이 아니라 고정 어휘(상태명 7종·layout 8 제목·칩 6종)라 조회표가 필요 없다 —
// 심벌 하나가 문구 하나다(dh-04 Task 3 Phase B).
//
// 자산: firmware/src/fonts/images/<name>.bin(+.json) 을 빌드 직전 tools/embed_images.py 가
// lib/image_data/ 에 C 배열로 생성한다. 인스턴스(kImgStatusSueopjung 등)는 "image_data.h" 에 선언된다.
//
// 저장 형식: 행 우선, 행당 bytesPerRow 바이트, MSB 가 왼쪽 — Adafruit_GFX::drawBitmap 이 그대로
// 읽는 형식과 같다. 잉크 마스크 하나뿐이라 호출부가 원하는 색으로 찍는다(칩 바탕 사각형·색 반전은
// Task4 몫 — 스펙 "필요한 자산": RED 상태용 흰 글자·BLACK 상태용 검정 글자를 마스크 하나로 겸한다).
//
// 좌표 규약: baseline 은 **이미지 윗변에서 베이스라인까지**(px) — bitmap_font.h 의 BitmapFont::baseline
// 과 같은 규약이다. 크기가 다른 요소(상태명 78px + 보조 문구 20px, 칩 16px + 주변 텍스트)를
// 베이스라인/세로 중앙으로 맞추려면 top = targetBaselineY - baseline 로 계산한다.
#include <cstdint>

struct BitmapImage {
  const uint8_t* bitmap;
  uint16_t w;
  uint16_t h;
  uint8_t bytesPerRow;
  uint8_t baseline;
};
