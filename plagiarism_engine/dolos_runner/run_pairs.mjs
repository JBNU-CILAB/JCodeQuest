#!/usr/bin/env node
// stdin: {"files":[{"id":"123","content":"..."}], "language":"python"}
// stdout: {"pairs":[{a_id,b_id,similarity,longest_fragment,total_overlap,fragments:[{a_lines:[s,e],b_lines:[s,e]}]}]}
//
// @dodona/dolos-lib 로 pairwise 구조 유사도를 산출한다. 라이브러리 버전에 따라 일부 필드명이
// 다를 수 있어(longest/overlap 등) 방어적으로 접근한다. 실패는 비0 종료 + stderr로 전파 →
// Python(dolos.py)이 run을 failed로 마감한다.

function readStdin() {
  return new Promise((resolve, reject) => {
    let buf = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (c) => (buf += c));
    process.stdin.on("end", () => resolve(buf));
    process.stdin.on("error", reject);
  });
}

const EXT = { python: "py", javascript: "js", java: "java", c: "c", cpp: "cpp", csharp: "cs" };

function pick(obj, ...keys) {
  for (const k of keys) if (obj && obj[k] != null) return obj[k];
  return undefined;
}

async function main() {
  const input = JSON.parse(await readStdin());
  const files = input.files || [];
  const language = input.language || "python";
  if (files.length < 2) {
    process.stdout.write(JSON.stringify({ pairs: [] }));
    return;
  }

  const lib = await import("@dodona/dolos-lib");
  const Dolos = lib.Dolos;
  const File = lib.File;
  const ext = EXT[language] || "txt";

  // File 클래스가 있으면 그것으로, 없으면 {path,content} 평문으로 — 버전 호환.
  const toFile = (f) => {
    const path = `${f.id}.${ext}`;
    if (File && typeof File === "function") {
      try { return new File(path, f.content); } catch { /* fallthrough */ }
    }
    return { path, content: f.content };
  };
  const dolosFiles = files.map(toFile);

  const dolos = new Dolos({ language });
  const report = await dolos.analyze(dolosFiles);

  const stripExt = (p) => String(p).replace(/\.[^.]+$/, "");
  const sel = (s) => (s ? [s.startRow ?? s.startLine ?? null, s.endRow ?? s.endLine ?? null] : [null, null]);

  const pairs = [];
  for (const pair of report.allPairs()) {
    let fragments = [];
    try {
      const frags = typeof pair.buildFragments === "function" ? pair.buildFragments() : [];
      fragments = (frags || []).map((fr) => ({
        a_lines: sel(pick(fr, "leftSelection", "leftkgrams", "left")),
        b_lines: sel(pick(fr, "rightSelection", "rightkgrams", "right")),
      }));
    } catch { /* fragments optional */ }

    const leftPath = pick(pair.leftFile || {}, "path") ?? pick(pair, "leftPath");
    const rightPath = pick(pair.rightFile || {}, "path") ?? pick(pair, "rightPath");
    pairs.push({
      a_id: stripExt(leftPath),
      b_id: stripExt(rightPath),
      similarity: pick(pair, "similarity") ?? 0,
      longest_fragment: pick(pair, "longest", "longestFragment") ?? 0,
      total_overlap: pick(pair, "overlap", "totalOverlap") ?? 0,
      fragments,
    });
  }
  process.stdout.write(JSON.stringify({ pairs }));
}

main().catch((e) => {
  process.stderr.write(String((e && e.stack) || e));
  process.exit(1);
});
