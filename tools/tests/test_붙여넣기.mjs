// 엑셀에서 실제로 복사되는 형태를 견디는지 본다. 등장인물은 전부 가상이다.
//
// 이 케이스들은 클립보드 실측에서 나왔다 — 엑셀이 클립보드에 넣는 텍스트는
// 화면에 보이는 값이 아니라 셀 서식이 입혀진 값이고, 셀 안 줄바꿈은 따옴표로
// 감싸여 온다. 붙여넣기 경로든 클립보드 경로든 같은 문자열을 받으므로
// 여기서 깨지면 두 경로가 함께 깨진다.
import { loadTools, reporter } from "./harness.mjs";

const { ROSTER } = loadTools();
const { ok, done } = reporter();

function parse(text) {
  const rows = ROSTER.splitRows(text);
  const cols = ROSTER.pickColumns(rows);
  if (!cols) return null;
  return cols.body
    .map(r => ({ 학번: (r[cols.id] || "").replace(/[\s,]/g, ""), 이름: (r[cols.name] || "").trim() }))
    .filter(s => s.학번 && s.이름);
}

// ── 셀 안 줄바꿈 (Alt+Enter) ────────────────────────────────
{
  const got = parse('30101\t"가상\n한겨울"\n30102\t가상김하늘');
  ok(got && got.length === 2, "줄바꿈 든 셀이 한 사람으로 읽힌다", JSON.stringify(got));
  ok(got && got[0].이름 === "가상\n한겨울", "이름이 쪼개지지 않는다", JSON.stringify(got?.[0]));
  ok(got && got[1].학번 === "30102", "다음 사람이 밀리지 않는다", JSON.stringify(got?.[1]));
}

// ── 셀 서식이 값에 섞여 온다 ─────────────────────────────────
{
  const got = parse("30,101\t가상김하늘\n30,102\t가상이서준");
  ok(got && got.length === 2, "천 단위 구분이 든 학번을 읽는다", JSON.stringify(got));
  ok(got && got[0].학번 === "30101", "쉼표를 떼고 학번으로 삼는다", JSON.stringify(got?.[0]));
}

// ── 따옴표 안 탭 ────────────────────────────────────────────
{
  const got = parse('30101\t"가상\t김하늘"\n30102\t가상이서준');
  ok(got && got.length === 2, "따옴표 안 탭이 열을 쪼개지 않는다", JSON.stringify(got));
}

// ── 이중 따옴표 이스케이프 ("" → ") ──────────────────────────
{
  const got = parse('30101\t"가상 ""별명"" 김하늘"\n30102\t가상이서준');
  ok(got && got[0].이름.includes('"별명"'), '따옴표 두 개는 한 개로 푼다', JSON.stringify(got?.[0]));
}

// ── 회귀: 따옴표가 없는 평범한 입력은 종전대로 ────────────────
{
  const got = parse("학번\t이름\n30101\t가상김하늘\n30102\t가상이서준");
  ok(got && got.length === 2 && got[0].학번 === "30101", "헤더 있는 평범한 탭 입력", JSON.stringify(got));
}
{
  const got = parse("30101   가상김하늘\n30102   가상이서준");
  ok(got && got.length === 2, "공백 구분(탭 없음)은 종전 경로", JSON.stringify(got));
}
{
  const got = parse("학번,이름\n30101,가상김하늘\n30102,가상이서준");
  ok(got && got.length === 2, "쉼표 구분(탭 없음)은 종전 경로", JSON.stringify(got));
}

// ── 점수에도 같은 규칙 ───────────────────────────────────────
{
  const rows = ROSTER.splitRows('30101\t1,250\n30102\t980');
  ok(rows.length === 2 && rows[0][1] === "1,250", "점수 쪽도 행이 유지된다", JSON.stringify(rows));
}

done();
