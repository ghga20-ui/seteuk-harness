// 명렬 붙여넣기의 열 판별을 검증한다. 등장인물은 전부 가상이다.
import { loadTools, reporter } from "./harness.mjs";

const { ROSTER } = loadTools();
const { ok, done } = reporter();

function run(label, text, expect) {
  const rows = ROSTER.splitRows(text);
  const cols = ROSTER.pickColumns(rows);
  if (!cols) {
    ok(!!expect.fail, `${label} → 판별 실패`);
    return;
  }
  const students = cols.body
    .map(r => ({ 학번: (r[cols.id] || "").replace(/\s+/g, ""), 이름: (r[cols.name] || "").trim() }))
    .filter(s => s.학번 && s.이름);
  const good =
    !expect.fail &&
    students.length === expect.n &&
    students[0].학번 === expect.first[0] &&
    students[0].이름 === expect.first[1];
  ok(good, `${label} (${cols.via})`,
     `→ ${students.length}명, 첫행 ${students[0]?.학번}/${students[0]?.이름}`);
}

// 엑셀에서 두 열을 긁으면 탭으로 구분된다
run("탭 · 헤더 있음", "학번\t이름\n30101\t김가상\n30102\t이가상\n30103\t박가상",
  { n: 3, first: ["30101", "김가상"] });

run("탭 · 헤더 없음", "30101\t김가상\n30102\t이가상",
  { n: 2, first: ["30101", "김가상"] });

run("이름이 앞 열", "김가상\t30101\n이가상\t30102",
  { n: 2, first: ["30101", "김가상"] });

// 반·번호·학번·이름이 함께 있으면 출석번호가 아니라 5자리 학번을 골라야 한다
run("반·번호·학번·이름 4열", "2\t1\t30101\t김가상\n2\t2\t30102\t이가상",
  { n: 2, first: ["30101", "김가상"] });

run("공백 구분", "30101   김가상\n30102   이가상",
  { n: 2, first: ["30101", "김가상"] });

run("CSV", "학번,이름\n30101,김가상\n30102,이가상",
  { n: 2, first: ["30101", "김가상"] });

run("다문화 이름", "30101\t응우옌티탄흐엉\n30102\t김가상",
  { n: 2, first: ["30101", "응우옌티탄흐엉"] });

run("빈 줄 섞임", "30101\t김가상\n\n30102\t이가상\n",
  { n: 2, first: ["30101", "김가상"] });

run("출석번호만 있는 표", "번호\t이름\n1\t김가상\n2\t이가상",
  { n: 2, first: ["1", "김가상"] });

run("이름만 있음(학번 없음)", "김가상\n이가상", { fail: true });

done();
