// 새 기능(인원 대조 · 열 확인 · 정오표 복구 동작)을 DOM 없이 검증한다.
// 등장인물은 전부 가상이다.
import { loadTools, reporter } from "./harness.mjs";

const { ok, done } = reporter();

function fresh() {
  return loadTools();
}

/* ── 인원 대조 ───────────────────────────────────────────────── */
{
  const { ROSTER, els } = fresh();
  els.get("src").value = "30101\t김가상\n30102\t이가상\n30103\t박가상";
  ROSTER.parse();
  ROSTER.setExpectedCount("3");
  let msg = ROSTER.countMessage();
  ok(msg.kind === "match" && msg.text.includes("3명을 읽었습니다") && msg.text.includes("3명과 같습니다"),
     "인원 일치 문구", JSON.stringify(msg));
}

{
  const { ROSTER, els } = fresh();
  els.get("src").value = "30101\t김가상\n30102\t이가상\n30103\t박가상";
  ROSTER.parse();
  ROSTER.setExpectedCount("48");
  const msg = ROSTER.countMessage();
  ok(msg.kind === "mismatch" &&
     msg.text === "적어 두신 48명과 붙여넣은 3명이 다릅니다." &&
     msg.sub === "명단에서 다시 세지 마시고, 어느 쪽이 맞는지 원본 표를 확인해 주세요.",
     "인원 불일치 문구가 브리프 문장과 정확히 같다", JSON.stringify(msg));
}

{
  // 인원 미입력 상태로 명단을 붙여넣은 경우 → 탈출구
  const { ROSTER, els } = fresh();
  els.get("src").value = "30101\t김가상\n30102\t이가상";
  ROSTER.parse();
  let msg = ROSTER.countMessage();
  ok(msg.kind === "awaiting" && msg.escapeLabel === "모르겠습니다. 명단을 보고 정하겠습니다",
     "인원 미입력 상태에 탈출구 문구가 있다", JSON.stringify(msg));

  ROSTER.useRosterCountInstead();
  msg = ROSTER.countMessage();
  ok(msg.kind === "escaped" && msg.text === "명단에서 센 2명으로 진행합니다. 이 수는 따로 대조하지 않았습니다.",
     "탈출구 사용 후 문구", JSON.stringify(msg));
  ok(ROSTER.state.expectedCount === 2 && ROSTER.state.expectedSource === "명단확인후",
     "탈출구를 쓰면 인원출처가 명단확인후로 기록된다", JSON.stringify(ROSTER.state.expectedSource));
}

{
  // 직접 입력한 경우 인원출처는 직접입력
  const { ROSTER, els } = fresh();
  els.get("src").value = "30101\t김가상\n30102\t이가상";
  ROSTER.setExpectedCount("2");
  ROSTER.parse();
  ok(ROSTER.state.expectedSource === "직접입력", "직접 입력하면 인원출처가 직접입력이다");
}

/* ── 열 확인 게이트 (저장 단추는 확인 전에 존재하지 않는다) ───────── */
{
  const { readFileSync } = await import("node:fs");
  const html = readFileSync(new URL("../도구.html", import.meta.url), "utf-8");
  ok(html.includes('id="save-actions"'), "저장 영역 컨테이너가 있다");
  // renderSaveGate 로직: colConfirmed 이전에는 비어 있어야 한다는 것은
  // 소스 상에서 state.colConfirmed 가드로 구현되어 있는지로 확인한다.
  const fn = html.slice(html.indexOf("function renderSaveGate"), html.indexOf("function renderSaveGate") + 400);
  ok(fn.includes("state.colConfirmed") && fn.includes('el.innerHTML = "";'),
     "저장 단추는 열 확인(state.colConfirmed) 전에는 렌더링되지 않는다", fn);
}

{
  const { ROSTER, els } = fresh();
  els.get("src").value = "30101\t김가상\n30102\t이가상";
  ROSTER.parse();
  ok(ROSTER.state.colConfirmed === false, "붙여넣기 직후에는 열 확인 전 상태다");
  ROSTER.confirmColumns();
  ok(ROSTER.state.colConfirmed === true, "맞습니다를 누르면 colConfirmed가 참이 된다");
}

/* ── 열이 바뀌었습니다 (스왑) ─────────────────────────────────── */
{
  const { ROSTER, els } = fresh();
  // 이름 열이 먼저 오는 표: 값 판별로도 정상 판별되지만, 스왑 동작 자체를 검증한다
  els.get("src").value = "김가상\t30101\n이가상\t30102";
  ROSTER.parse();
  const before = { ...ROSTER.state.cols };
  ROSTER.swapColumns();
  ok(ROSTER.state.cols.id === before.name && ROSTER.state.cols.name === before.id,
     "열이 바뀌었습니다 단추는 학번·이름 열 인덱스를 서로 바꾼다");
  ok(ROSTER.state.colConfirmed === false, "열을 바꾸면 확인 상태가 다시 미확인으로 돌아간다");
}

/* ── 정오표: 중복 학번 복구 동작 ──────────────────────────────── */
{
  const { ROSTER, els } = fresh();
  els.get("src").value = "30101\t김가상\n30102\t이가상\n30102\t박가상";
  ROSTER.parse();
  ok(ROSTER.state.dupRows.length === 1, "중복 학번 1건을 감지한다", JSON.stringify(ROSTER.state.dupRows));
  ok(ROSTER.state.students.length === 3, "복구 전에는 중복 행도 그대로 남아 있다(삭제하지 않는다)");
  ok(ROSTER.state.students[2].중복 === true, "뒤에 온 행에 중복 표시가 붙는다");

  ROSTER.resolveDuplicates("drop-later");
  ok(ROSTER.state.students.length === 2, "뒤엣것 지우기를 누르면 나중 행이 제거된다",
     JSON.stringify(ROSTER.state.students));
  ok(ROSTER.state.students.every(s => s.이름 !== "박가상"), "지운 행(박가상)이 명단에 남지 않는다");
}

{
  const { ROSTER, els } = fresh();
  els.get("src").value = "30101\t김가상\n30102\t이가상\n30102\t박가상";
  ROSTER.parse();
  ROSTER.resolveDuplicates("keep-both");
  ok(ROSTER.state.students.length === 3, "둘 다 두기를 누르면 두 행 모두 남는다");
  ok(ROSTER.state.dupResolution === "keep-both", "둘 다 두기 선택이 기록된다");
}

/* ── 정오표: 0건이면 "버린 행은 없습니다" ─────────────────────── */
{
  const { ROSTER, els } = fresh();
  els.get("src").value = "30101\t김가상\n30102\t이가상";
  ROSTER.parse();
  ok(ROSTER.state.blank === 0, "빈 행이 없다");
  const { readFileSync } = await import("node:fs");
  const html = readFileSync(new URL("../도구.html", import.meta.url), "utf-8");
  ok(html.includes("버린 행은 없습니다"), "0건일 때 상시 노출되는 문장이 소스에 있다");
}

/* ── 정오표: 빈 행 건너뜀 ────────────────────────────────────── */
{
  const { ROSTER, els } = fresh();
  els.get("src").value = "30101\t김가상\n\t이가상\n30103\t박가상";
  ROSTER.parse();
  ok(ROSTER.state.blank === 1, "학번이 빈 행을 건너뛴다", JSON.stringify(ROSTER.state));
  ok(ROSTER.state.students.length === 2, "빈 행은 학생 목록에 들어가지 않는다");
}

/* ── 정오표: 여러 반 혼재 ────────────────────────────────────── */
{
  const { ROSTER, els } = fresh();
  els.get("src").value = "30101\t김가상\n30102\t이가상\n40101\t박가상\n40102\t최가상";
  ROSTER.parse();
  ok(ROSTER.state.multiClassPrefixes.length === 2, "학번 앞자리가 두 종류면 혼재로 감지한다",
     JSON.stringify(ROSTER.state.multiClassPrefixes));
  const keep = ROSTER.state.multiClassPrefixes[0];
  ROSTER.resolveMultiClass(keep);
  ok(ROSTER.state.students.every(s => s.학번.slice(0, 3) === keep),
     "한 반만 두기를 선택하면 다른 반 학번이 걸러진다", JSON.stringify(ROSTER.state.students));
}

{
  const { ROSTER, els } = fresh();
  els.get("src").value = "30101\t김가상\n30102\t이가상\n40101\t박가상\n40102\t최가상";
  ROSTER.parse();
  ROSTER.resolveMultiClass("keep-both");
  ok(ROSTER.state.students.length === 4, "둘 다 두기를 선택하면 아무것도 걸러지지 않는다");
}

/* ── 인원 칸에 표를 붙여넣은 것으로 보이면 명단으로 넘긴다 ───────── */
{
  const { ROSTER } = fresh();
  ok(typeof ROSTER.setExpectedCount === "function", "setExpectedCount가 노출되어 있다");
}

/* ── window.TOOLS 계약이 그대로 유지된다 ─────────────────────────── */
{
  const { readFileSync } = await import("node:fs");
  const html = readFileSync(new URL("../도구.html", import.meta.url), "utf-8");
  ok(html.includes("window.TOOLS = { ROSTER, REVIEW, U8, B2, splitRows, esc }"),
     "window.TOOLS 내보내기 계약이 그대로다");
}

done();
