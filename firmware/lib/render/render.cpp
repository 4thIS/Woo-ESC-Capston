#include "render.h"

#include <cstdio>

#include "font_data.h"
#include "image_data.h"
#include "render_colors.h"
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

void drawInfoA(Adafruit_GFX& g, const RenderModel& m) {
  g.drawFastHLine(0, kDivider1Y, kSplitX, GxEPD_BLACK);
  g.drawFastHLine(0, kDivider2Y, kSplitX, GxEPD_BLACK);
  const int16_t subjW = drawInfoRow(g, 0, "과목명", m.cur.subj);
  if (m.cur.flags & 0x02)
    drawChip(g, kImgChipByeongyeong, (int16_t)(kValueX + subjW + 10),
             (int16_t)(kInfoRowBase[0] - kInfoChipLift));
  drawInfoRow(g, 1, "담당교수", m.cur.prof);
  char s[6], e[6], range[24];
  formatHM(m.cur.sH, m.cur.sM, s, sizeof s);
  formatHM(m.cur.eH, m.cur.eM, e, sizeof e);
  snprintf(range, sizeof range, "%s \xE2\x80\x93 %s", s, e);  // U+2013 en dash
  drawInfoRow(g, 2, "강의시간", range);
}

void drawInfoB(Adafruit_GFX& g, const RenderModel& m) {
  if (!(m.next.flags & 0x01)) {
    drawText(g, kNanum28Bold, "오늘 일정 없음", kPad, kNoScheduleBase, GxEPD_BLACK, kTrack28);
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
    char more[24];
    if (r == 0 && w.moreAbove > 0) {
      snprintf(more, sizeof more, "\xE2\x86\x91 %u개 더", (unsigned)w.moreAbove);  // ↑
      drawText(g, kNanum16Regular, more, x0, base, GxEPD_BLACK);
      continue;
    }
    if (r == w.rows - 1 && w.moreBelow > 0) {
      snprintf(more, sizeof more, "\xE2\x86\x93 %u개 더", (unsigned)w.moreBelow);  // ↓
      drawText(g, kNanum16Regular, more, x0, base, GxEPD_BLACK);
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
    if (chip != nullptr)
      drawImage(g, *chip, (int16_t)(kListX + kListW - kListPadX - chip->w), (int16_t)(base - chip->baseline),
                fg);
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
  const bool hasTag = m.newTag[0] != ' ';
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
