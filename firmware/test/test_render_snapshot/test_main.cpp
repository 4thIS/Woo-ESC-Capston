#include <unity.h>

#include <algorithm>
#include <filesystem>
#include <string>
#include <system_error>
#include <vector>

#include "fixture_parse.h"
#include "host_gfx.h"
#include "render.h"
#include "snapshot.h"

// 렌더 스냅샷 — test/fixtures/render/*.json 전부를 그려 snapshots/<이름>.png 정답과 픽셀 단위로 대조한다.
// 화면을 의도해서 바꿨으면 `python tools/render_preview.py --update-snapshots` 로 정답을 다시 만든다
// (바뀐 정답 PNG 가 PR diff 에 그대로 보인다). CWD 는 firmware/.
// 실패 메시지는 ASCII 로 쓴다 — Unity 가 비ASCII 바이트를 이스케이프해 출력해서 한글이 읽히지 않는다.
namespace fs = std::filesystem;

static const char* kFixtureDir = "test/fixtures/render";
static const char* kSnapshotDir = "test/fixtures/render/snapshots";
static const char* kOutDir = "test/fixtures/render/_out";

// dir 안의 ext 파일 stem 을 이름순으로. 폴더가 없으면 빈 목록.
static std::vector<std::string> stems(const char* dir, const char* ext) {
  std::vector<std::string> out;
  std::error_code ec;
  for (fs::directory_iterator it(dir, ec), end; !ec && it != end; it.increment(ec))
    if (it->is_regular_file() && it->path().extension() == ext) out.push_back(it->path().stem().string());
  std::sort(out.begin(), out.end());
  return out;
}

static bool render(const std::string& stem, HostGfx& g) {
  RenderModel m{};
  char name[64];
  const std::string path = std::string(kFixtureDir) + "/" + stem + ".json";
  if (!parseFixtureFile(path.c_str(), m, name, sizeof(name))) return false;
  renderLayout(g, m);
  return true;
}

void test_snapshots_match() {
  const std::vector<std::string> fixtures = stems(kFixtureDir, ".json");
  TEST_ASSERT_TRUE_MESSAGE(!fixtures.empty(), "no fixtures found - is CWD firmware/?");
  std::string failures;
  for (const std::string& s : fixtures) {
    HostGfx g;
    std::string line;
    if (!render(s, g)) {
      line = s + ": fixture parse failed";
    } else {
      const std::string base = std::string(kSnapshotDir) + "/" + s + ".png";
      const SnapshotDiff d = compareToBaseline(g, base.c_str());
      if (!d.baselineLoaded && d.baselineW > 0) {
        line = s + ": baseline is " + std::to_string(d.baselineW) + "x" + std::to_string(d.baselineH) +
               ", expected " + std::to_string(g.width()) + "x" + std::to_string(g.height()) +
               " - check the PNG before regenerating";
      } else if (!d.baselineLoaded) {
        line =
            s +
            ": no baseline (missing or unreadable) - run python tools/render_preview.py --update-snapshots";
      } else if (d.diffPixels > 0) {
        std::error_code ec;
        fs::create_directories(kOutDir, ec);
        const std::string diff = std::string(kOutDir) + "/" + s + "_diff.png";
        saveDiffPNG(g, base.c_str(), diff.c_str());
        line = s + ": " + std::to_string(d.diffPixels) + " px differ -> _out/" + s + "_diff.png";
      }
    }
    if (!line.empty()) {
      TEST_MESSAGE(line.c_str());
      failures += line + "\n";
    }
  }
  if (!failures.empty()) TEST_FAIL_MESSAGE(failures.c_str());
}

void test_no_orphan_snapshots() {
  const std::vector<std::string> fixtures = stems(kFixtureDir, ".json");
  std::string orphans;
  for (const std::string& s : stems(kSnapshotDir, ".png"))
    if (!std::binary_search(fixtures.begin(), fixtures.end(), s)) orphans += s + ".png ";
  if (!orphans.empty()) TEST_FAIL_MESSAGE(("baseline without fixture: " + orphans).c_str());
}

// 화면 스펙은 battMv 를 일부러 그리지 않는다(terminal-epaper.md "배터리 전압"). 저전압이어도 화면이 같아야
// 한다 — edge_low_battery.json 은 layout1_class.json 과 batt_mv 만 다르다.
void test_low_battery_screen_identical() {
  HostGfx normal, low;
  TEST_ASSERT_TRUE(render("layout1_class", normal));
  TEST_ASSERT_TRUE(render("edge_low_battery", low));
  long diff = 0;
  for (int16_t y = 0; y < normal.height(); y++)
    for (int16_t x = 0; x < normal.width(); x++)
      if (normal.pixelAt(x, y) != low.pixelAt(x, y)) diff++;
  TEST_ASSERT_EQUAL(0, diff);
}

void setUp() {}
void tearDown() {}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_snapshots_match);
  RUN_TEST(test_no_orphan_snapshots);
  RUN_TEST(test_low_battery_screen_identical);
  return UNITY_END();
}
