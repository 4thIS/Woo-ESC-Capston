#include "render.h"

#include <cstdio>

#include "epd_colors.h"
#include "font_data.h"
#include "image_data.h"
#include "render_logic.h"
#include "text.h"

namespace {

// 골격 — terminal-epaper.md "골격 — 고정 좌표"
constexpr int16_t kW = 800;
constexpr int16_t kH = 480;
constexpr int16_t kPad = 24;
constexpr int16_t kHeaderLineY = 50;
constexpr int16_t kBandY = 52;
constexpr int16_t kBandW = 500;
constexpr int16_t kBandH = 164;
constexpr int16_t kBandLineY = 214;
constexpr int16_t kInfoY = 216;
constexpr int16_t kInfoH = 224;
constexpr int16_t kDivider1Y = 291;
constexpr int16_t kDivider2Y = 365;
constexpr int16_t kSplitX = 498;
constexpr int16_t kListX = 500;
constexpr int16_t kListW = 300;
constexpr int16_t kListPadX = 18;
constexpr int16_t kListPadY = 16;
constexpr int16_t kFooterY = 440;
constexpr int16_t kFooterH = 40;

// 영역별 규격
constexpr int16_t kRoomToHoGap = 10;
constexpr int16_t kBandGap = 8;  // 상태명 ↔ 보조 문구
constexpr int16_t kLabelX = 24;  // 정보 라벨열 x 24–128
constexpr int16_t kValueX = 146;
constexpr int16_t kRowH = 36;   // 오늘 목록 행 높이
constexpr int16_t kTimeW = 46;  // 목록 시작 시각 폭
constexpr int16_t kTimeGap = 8;
constexpr int16_t kChipH = 22;  // "오늘" 칩
constexpr int16_t kChipGap = 10;
constexpr int16_t kChipPadX = 6;       // ⚠️ 스펙에 없음 — 칩 좌우 여백
constexpr int16_t kChipTextBase = 17;  // ⚠️ 칩 윗변 → 칩 글자 베이스라인

// 자간(px) — 78·62·32 px -0.03~-0.04 em, 28 px -0.02 em. 반올림한 정수.
constexpr int8_t kTrack28 = -1;
constexpr int8_t kTrack32 = -1;
constexpr int8_t kTrack62 = -2;

// ⚠️ 세로 위치 초기값(베이스라인) — 첫 PNG 검토에서 조정한다.
constexpr int16_t kHeaderBase = 37;
constexpr int16_t kInfoRowBase[3] = {263, 338, 413};
constexpr int16_t kRowTextBase = 25;  // 목록 행 윗변 → 글자 베이스라인
constexpr int16_t kFooterBase = kFooterY + 26;

void drawImage(Adafruit_GFX& g, const BitmapImage& img, int16_t x, int16_t top, uint16_t color) {
  g.drawBitmap(x, top, img.bitmap, (int16_t)img.w, (int16_t)img.h, color);
}

// 흑 채움 칩 + 흰 글자 마스크. 반환: 칩 폭.
int16_t drawChip(Adafruit_GFX& g, const BitmapImage& img, int16_t x, int16_t boxTop) {
  const int16_t w = (int16_t)(img.w + 2 * kChipPadX);
  g.fillRect(x, boxTop, w, kChipH, GxEPD_BLACK);
  drawImage(g, img, (int16_t)(x + kChipPadX), (int16_t)(boxTop + kChipTextBase - img.baseline), GxEPD_WHITE);
  return w;
}

void drawHeader(Adafruit_GFX& g, const RenderModel& m) {
  g.fillRect(0, kHeaderLineY, kW, 2, GxEPD_BLACK);
  char room[6];
  snprintf(room, sizeof room, "%u", (unsigned)m.room);
  const int16_t w = drawText(g, kNanum32ExtraBold, room, kPad, kHeaderBase, GxEPD_BLACK, kTrack32);
  drawText(g, kNanum16Regular, "호", (int16_t)(kPad + w + kRoomToHoGap), kHeaderBase, GxEPD_BLACK);
  const char* wd = weekdayName(m.weekday);
  drawText(g, kNanum20Regular, wd, (int16_t)(kW - kPad - textWidth(kNanum20Regular, wd)), kHeaderBase,
           GxEPD_BLACK);
}

void drawStatusBand(Adafruit_GFX& g, const RenderModel& m) {
  const BandStyle style = bandStyle(m.layout);
  const uint16_t fg = style == BandStyle::Red ? GxEPD_WHITE : GxEPD_BLACK;
  if (style == BandStyle::Red)
    g.fillRect(0, kBandY, kBandW, kBandH, GxEPD_RED);
  else
    g.fillRect(0, kBandLineY, kBandW, 2, GxEPD_BLACK);
  const BitmapImage* img = statusImage(m.layout);
  if (img == nullptr) return;
  char sub[32];
  const bool hasSub = statusSubline(m, sub, sizeof sub);
  const int16_t blockH = (int16_t)(img->h + (hasSub ? kBandGap + kNanum20Regular.cellH : 0));
  const int16_t top = (int16_t)(kBandY + (kBandH - blockH) / 2);
  drawImage(g, *img, kPad, top, fg);
  if (hasSub)
    drawText(g, kNanum20Regular, sub, kPad, (int16_t)(top + img->h + kBandGap + kNanum20Regular.baseline),
             fg);
}

constexpr int16_t kInfoChipLift = 18;     // ⚠️ 값 베이스라인 → 변경 칩 윗변
constexpr int16_t kNextLabelGap = 10;     // "다음 수업" ↔ 아래 줄
constexpr int16_t kNextTimeGap = 16;      // 시작 시각 ↔ 과목명
constexpr int16_t kNoScheduleBase = 338;  // ⚠️ 정보 영역 세로 중앙

int16_t drawInfoRow(Adafruit_GFX& g, int row, const char* label, const char* value) {
  drawText(g, kNanum20Regular, label, kLabelX, kInfoRowBase[row], GxEPD_BLACK);
  return drawText(g, kNanum28Bold, value, kValueX, kInfoRowBase[row], GxEPD_BLACK, kTrack28);
}

// 정보 행 칸(구분선 제외) — 값이 넘칠 때 덮는 세로 범위. terminal-epaper.md 형태 A 넘침 규칙.
constexpr int16_t kInfoCellTop[3] = {kInfoY, kDivider1Y + 1, kDivider2Y + 1};
constexpr int16_t kInfoCellBottom[3] = {kDivider1Y, kDivider2Y, kFooterY};  // 미포함
constexpr int16_t kValueRight = 476;                                        // 값 영역 오른쪽 끝(x 146–476)
constexpr int16_t kInfoChipGap = 10;                                        // 값 ↔ 변경 칩

void drawInfoA(Adafruit_GFX& g, const RenderModel& m) {
  g.drawFastHLine(0, kDivider1Y, kSplitX, GxEPD_BLACK);
  g.drawFastHLine(0, kDivider2Y, kSplitX, GxEPD_BLACK);
  const int16_t subjW = drawInfoRow(g, 0, "과목명", m.cur.subj);
  if (m.cur.flags & 0x02) {
    // 넘치면 칩을 오른쪽 끝 x 476 에 붙이고, 칩 자리(앞 간격 포함)를 백으로 먼저 덮는다 — 칩이 이긴다.
    const int16_t chipW = (int16_t)(kImgChipByeongyeong.w + 2 * kChipPadX);
    int16_t chipX = (int16_t)(kValueX + subjW + kInfoChipGap);
    if (chipX + chipW > kValueRight) {
      chipX = (int16_t)(kValueRight - chipW);
      g.fillRect((int16_t)(chipX - kInfoChipGap), kInfoCellTop[0], (int16_t)(chipW + kInfoChipGap),
                 (int16_t)(kInfoCellBottom[0] - kInfoCellTop[0]), GxEPD_WHITE);
    }
    drawChip(g, kImgChipByeongyeong, chipX, (int16_t)(kInfoRowBase[0] - kInfoChipLift));
  }
  // layout 7(대여중)은 cur.prof 자리에 예약자 이름이 온다. 학생 웹 예약은 서버가 이름을 싣지 않아(공개 화면)
  // 비어 오므로 "학생"으로 대신한다(#124, terminal-epaper.md 형태 A).
  if (m.layout == 7)
    drawInfoRow(g, 1, "예약자", m.cur.prof[0] ? m.cur.prof : "학생");
  else
    drawInfoRow(g, 1, "담당교수", m.cur.prof);
  char s[6], e[6], range[24];
  formatHM(m.cur.sH, m.cur.sM, s, sizeof s);
  formatHM(m.cur.eH, m.cur.eM, e, sizeof e);
  snprintf(range, sizeof range, "%s \xE2\x80\x93 %s", s, e);  // U+2013 en dash
  drawInfoRow(g, 2, "강의시간", range);
  // 값 영역을 넘친 글자가 분할선 너머 목록 칸에 남지 않게 x 476 오른쪽 행 칸을 백으로(목록·분할선은 이후에
  // 그린다).
  for (int r = 0; r < 3; r++)
    g.fillRect(kValueRight, kInfoCellTop[r], (int16_t)(kW - kValueRight),
               (int16_t)(kInfoCellBottom[r] - kInfoCellTop[r]), GxEPD_WHITE);
}

void drawInfoB(Adafruit_GFX& g, const RenderModel& m) {
  if (!(m.next.flags & 0x01)) {
    // "남은" — 하루가 끝나도 옆 목록에는 그날 수업이 보이므로 "오늘 일정 없음"은 모순으로 읽힌다.
    drawText(g, kNanum28Bold, "오늘 남은 수업 없음", kPad, kNoScheduleBase, GxEPD_BLACK, kTrack28);
    return;
  }
  const int16_t blockH = (int16_t)(kNanum20Regular.cellH + kNextLabelGap + kNanum62ExtraBold.cellH);
  const int16_t top = (int16_t)(kInfoY + (kInfoH - blockH) / 2);
  drawText(g, kNanum20Regular, "다음 수업", kPad, (int16_t)(top + kNanum20Regular.baseline), GxEPD_BLACK);
  const int16_t base = (int16_t)(top + kNanum20Regular.cellH + kNextLabelGap + kNanum62ExtraBold.baseline);
  char hm[6];
  formatHM(m.next.sH, m.next.sM, hm, sizeof hm);
  const int16_t tw = drawText(g, kNanum62ExtraBold, hm, kPad, base, GxEPD_BLACK, kTrack62);
  drawText(g, kNanum28Bold, m.next.subj, (int16_t)(kPad + tw + kNextTimeGap), base, GxEPD_BLACK, kTrack28);
  // 과목(ASCII 20자)이 분할선을 넘으면 목록 칸이 이긴다 — 형태 A 와 같은 규칙(#118). 형태 B 는 행 구분선이
  // 없어 정보 영역 세로 전체를 덮는다. 목록·분할선은 이후에 그린다.
  g.fillRect(kValueRight, kInfoY, (int16_t)(kW - kValueRight), kInfoH, GxEPD_WHITE);
}

constexpr int16_t kTypeChipGap = 8;  // 과목 ↔ type 약어(겹치면 이 폭까지 덮는다)
// 목록 잘림 표시 — 채운 삼각형(밑변 11 · 높이 6, 행 윗변 +15–20) + 간격 6 + "n개 더"(16/400).
// ↑·↓ 글리프는 16 px 에서 1 px 막대라 "↑ 4개 더"가 "14개 더"로 읽혔다(#89 layout 6, #91).
// 밑변은 홀수 — 1비트라 짝수면 꼭짓점이 반 픽셀 치우친다(#118, 꼭짓점 x 523).
constexpr int16_t kMoreTriBase = 11;
constexpr int16_t kMoreTriTop = 15;
constexpr int16_t kMoreTriBottom = 20;
constexpr int16_t kMoreTextGap = 6;

void drawMoreRow(Adafruit_GFX& g, int16_t x0, int16_t top, bool up, uint8_t count) {
  const int16_t xl = x0, xr = (int16_t)(x0 + kMoreTriBase - 1), xm = (int16_t)(x0 + (kMoreTriBase - 1) / 2);
  const int16_t yt = (int16_t)(top + kMoreTriTop), yb = (int16_t)(top + kMoreTriBottom);
  if (up)
    g.fillTriangle(xm, yt, xl, yb, xr, yb, GxEPD_BLACK);  // ▲ 위로 잘림
  else
    g.fillTriangle(xl, yt, xr, yt, xm, yb, GxEPD_BLACK);  // ▼ 아래로 잘림
  char more[16];
  snprintf(more, sizeof more, "%u개 더", (unsigned)count);
  drawText(g, kNanum16Regular, more, (int16_t)(x0 + kMoreTriBase + kMoreTextGap),
           (int16_t)(top + kRowTextBase), GxEPD_BLACK);
}

void drawTodayList(Adafruit_GFX& g, const RenderModel& m) {
  const int16_t x0 = kListX + kListPadX;
  const int16_t chipTop = kBandY + kListPadY;
  drawChip(g, kImgChipOneul, x0, chipTop);
  const int16_t rowsTop = chipTop + kChipH + kChipGap;
  const TodayWindow w = todayWindow(m);
  if (w.count == 0) {
    drawText(g, kNanum20Regular, "오늘 일정 없음", x0, (int16_t)(rowsTop + kRowTextBase), GxEPD_BLACK);
    return;
  }
  for (uint8_t r = 0; r < w.rows; r++) {
    const int16_t top = (int16_t)(rowsTop + r * kRowH);
    const int16_t base = (int16_t)(top + kRowTextBase);
    if (r == 0 && w.moreAbove > 0) {
      drawMoreRow(g, x0, top, true, w.moreAbove);
      continue;
    }
    if (r == w.rows - 1 && w.moreBelow > 0) {
      drawMoreRow(g, x0, top, false, w.moreBelow);
      continue;
    }
    const uint8_t i = (uint8_t)(w.start + r);
    const TodaySlot& t = m.today[i];
    const bool isCur = (int)i == (int)w.curIdx;
    const uint16_t fg = isCur ? GxEPD_WHITE : GxEPD_BLACK;
    if (isCur) g.fillRect(kListX, top, kListW, kRowH, GxEPD_BLACK);
    char hm[6];
    formatHM(t.sH, t.sM, hm, sizeof hm);
    drawText(g, kNanum16Regular, hm, x0, base, fg);
    drawText(g, isCur ? kNanum20Bold : kNanum20Regular, t.subj, (int16_t)(x0 + kTimeW + kTimeGap), base, fg);
    const BitmapImage* chip = typeChip(t.type);
    if (chip != nullptr) {
      // 과목이 길면(ASCII 20자) 약어 자리까지 닿는다 — 약어 앞 간격부터 행 오른쪽 끝(x 800)까지 행 높이
      // 전체를 바탕색으로 덮고 약어를 그린다. 약어 뒤 여백(18)까지 덮어야 넘친 과목 조각이 남지 않는다.
      const int16_t chipX = (int16_t)(kListX + kListW - kListPadX - chip->w);
      g.fillRect((int16_t)(chipX - kTypeChipGap), top, (int16_t)(kListX + kListW - (chipX - kTypeChipGap)),
                 kRowH, isCur ? GxEPD_BLACK : GxEPD_WHITE);
      drawImage(g, *chip, chipX, (int16_t)(base - chip->baseline), fg);
    }
  }
}

void drawFooter(Adafruit_GFX& g, const RenderModel& m) {
  g.fillRect(0, kFooterY, kW, kFooterH, GxEPD_BLACK);
  char s[32];
  const char bld = (m.bld >= 0x21 && m.bld <= 0x7E) ? m.bld : '?';
  snprintf(s, sizeof s, "%c \xC2\xB7 %u \xC2\xB7 U%u", bld, (unsigned)m.room, (unsigned)m.unit);  // U+00B7
  drawText(g, kNanum16Regular, s, kPad, kFooterBase, GxEPD_WHITE);
}

// layout 8 — terminal-epaper.md "layout 8 — 설정 대기 (전폭)"
constexpr int16_t kSetupPad = 48;
constexpr int16_t kSetupTitleGap = 8;   // 제목 ↔ 부제
constexpr int16_t kSetupBlockGap = 22;  // 부제 ↔ NEW 칩
constexpr int16_t kSetupChipPadY = 14;
constexpr int16_t kSetupChipPadX = 24;
constexpr int16_t kSetupChipTextGap = 20;  // NEW 칩 ↔ 안내 2줄
constexpr int16_t kSetupLineGap = 8;       // ⚠️ 안내 2줄 사이

void drawSetup(Adafruit_GFX& g, const RenderModel& m) {
  g.fillRect(0, kHeaderLineY, kW, 2, GxEPD_BLACK);
  drawText(g, kNanum20Bold, "미설정 단말", kPad, kHeaderBase, GxEPD_BLACK);

  const BitmapImage& title = kImgTitleSeoljeongdaegi;
  const bool hasTag = m.newTag[0] != '\0';
  const int16_t chipH = (int16_t)(2 * kSetupChipPadY + kNanum62ExtraBold.cellH);
  const int16_t blockH =
      (int16_t)(title.h + kSetupTitleGap + kNanum20Regular.cellH + (hasTag ? kSetupBlockGap + chipH : 0));
  const int16_t top = (int16_t)(kBandY + (kH - kBandY - blockH) / 2);
  drawImage(g, title, kSetupPad, top, GxEPD_BLACK);
  drawText(g, kNanum20Regular, "아직 어느 강의실에도 배정되지 않았습니다", kSetupPad,
           (int16_t)(top + title.h + kSetupTitleGap + kNanum20Regular.baseline), GxEPD_BLACK);
  if (!hasTag) return;

  const int16_t chipTop = (int16_t)(top + title.h + kSetupTitleGap + kNanum20Regular.cellH + kSetupBlockGap);
  const int16_t chipW = (int16_t)(textWidth(kNanum62ExtraBold, m.newTag, kTrack62) + 2 * kSetupChipPadX);
  g.fillRect(kSetupPad, chipTop, chipW, chipH, GxEPD_BLACK);
  drawText(g, kNanum62ExtraBold, m.newTag, (int16_t)(kSetupPad + kSetupChipPadX),
           (int16_t)(chipTop + kSetupChipPadY + kNanum62ExtraBold.baseline), GxEPD_WHITE, kTrack62);

  const int16_t tx = (int16_t)(kSetupPad + chipW + kSetupChipTextGap);
  const int16_t linesTop = (int16_t)(chipTop + (chipH - (2 * kNanum20Regular.cellH + kSetupLineGap)) / 2);
  drawText(g, kNanum20Regular, "관리자 화면에서", tx, (int16_t)(linesTop + kNanum20Regular.baseline),
           GxEPD_BLACK);
  drawText(g, kNanum20Regular, "이 번호를 강의실에 배정하세요", tx,
           (int16_t)(linesTop + kNanum20Regular.cellH + kSetupLineGap + kNanum20Regular.baseline),
           GxEPD_BLACK);
}

}  // namespace

void renderLayout(Adafruit_GFX& gfx, const RenderModel& m) {
  gfx.fillScreen(GxEPD_WHITE);
  if (m.layout == 8) {
    drawSetup(gfx, m);
    return;
  }
  if (m.layout < 1 || m.layout > 7) return;  // 범위 밖은 흰 화면(⚠️ 열린 질문 5)
  drawHeader(gfx, m);
  drawStatusBand(gfx, m);
  if (m.layout == 4)
    drawInfoB(gfx, m);
  else
    drawInfoA(gfx, m);
  drawTodayList(gfx, m);
  gfx.fillRect(kSplitX, kBandY, 2, (int16_t)(kFooterY - kBandY), GxEPD_BLACK);
  drawFooter(gfx, m);
}
