#include "fixture_parse.h"

#include <ArduinoJson.h>

#include <cstdio>
#include <cstring>
#include <string>

namespace {

// strncpy 는 src 가 cap 이상이면 널을 안 붙인다. RenderModel 을 영으로 초기화하지 않고
// 넘기는 호출자도 있을 수 있어(공개 API) 잘림 여부와 무관하게 여기서 항상 종단한다.
// subj[21]에 UTF-8 한글은 7글자면 차므로 잘림은 가정이 아니라 실제로 일어난다.
void copyStr(char* dest, size_t cap, const char* src) {
  if (cap == 0) return;
  strncpy(dest, src, cap - 1);
  dest[cap - 1] = '\0';
}

void readSlot(JsonObjectConst j, RenderSlot& s) {
  copyStr(s.subj, sizeof(s.subj), j["subj"] | "");
  copyStr(s.prof, sizeof(s.prof), j["prof"] | "");
  s.sH = j["s_h"] | 0;
  s.sM = j["s_m"] | 0;
  s.eH = j["e_h"] | 0;
  s.eM = j["e_m"] | 0;
  s.type = j["type"] | 0;
  s.flags = j["flags"] | 0;
}

}  // namespace

bool parseFixtureFile(const char* path, RenderModel& out, char* nameOut, size_t nameCap) {
  FILE* f = fopen(path, "rb");
  if (!f) return false;
  fseek(f, 0, SEEK_END);
  long sz = ftell(f);
  if (sz < 0) {  // ftell 실패 — 아래 std::string(sz, ...) 에 음수가 들어가는 것을 막는다
    fclose(f);
    return false;
  }
  fseek(f, 0, SEEK_SET);
  std::string buf((size_t)sz, '\0');
  size_t got = fread(buf.data(), 1, (size_t)sz, f);
  fclose(f);
  if (got != (size_t)sz) return false;

  JsonDocument doc;
  if (deserializeJson(doc, buf) != DeserializationError::Ok) return false;
  // `{}` 가 아닌 `[]`·`42`·`"str"` 도 유효한 JSON 이라 deserializeJson 은 성공을 돌려준다.
  // 그 뒤의 필드 접근은 전부 `| 0`/`| ""` 기본값으로 떨어지므로, 가드가 없으면 전부 0 인
  // RenderModel 이 true 와 함께 나간다 — 망가진 픽스처가 "에러 없음"으로 조용히 통과한다.
  if (!doc.is<JsonObjectConst>()) return false;

  copyStr(nameOut, nameCap, doc["name"] | "");
  out.layout = doc["layout"] | 0;
  const char* bld = doc["bld"] | "";
  out.bld = bld[0];
  out.room = doc["room"] | 0;
  out.unit = doc["unit"] | 0;
  copyStr(out.nowStr, sizeof(out.nowStr), doc["now_str"] | "");
  copyStr(out.dateStr, sizeof(out.dateStr), doc["date_str"] | "");
  out.weekday = doc["weekday"] | 0;
  readSlot(doc["prev"], out.prev);
  readSlot(doc["cur"], out.cur);
  readSlot(doc["next"], out.next);
  JsonArrayConst today = doc["today"];
  size_t i = 0;
  for (JsonObjectConst t : today) {
    if (i >= sizeof(out.today) / sizeof(out.today[0])) break;
    out.today[i].sH = t["s_h"] | 0;
    out.today[i].sM = t["s_m"] | 0;
    out.today[i].eH = t["e_h"] | 0;
    out.today[i].eM = t["e_m"] | 0;
    copyStr(out.today[i].subj, sizeof(out.today[i].subj), t["subj"] | "");
    out.today[i].type = t["type"] | 0;
    ++i;
  }
  // n_today 를 그대로 믿으면 today[] 항목 수보다 큰 값일 때 소비자가 미초기화 슬롯(또는
  // 배열 범위 밖)을 읽는다. 실제로 채운 개수(i, 이미 24 상한 적용됨)와 선언값 중 작은 쪽을 쓴다.
  long declared = doc["n_today"] | 0L;
  if (declared < 0) declared = 0;
  out.nToday = (uint8_t)((size_t)declared < i ? (size_t)declared : i);
  copyStr(out.newTag, sizeof(out.newTag), doc["new_tag"] | "");
  out.battMv = doc["batt_mv"] | 0;
  return true;
}
