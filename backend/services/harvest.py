"""
규격서 파일 수집 · 텍스트 추출 · 조항 분해

흐름
  URL -> 파일 다운로드 -> 텍스트 추출 -> 절/조항 단위 분해 -> 조항 후보 YAML

추출한 조항은 반드시 `출처: 수집` 으로 표시한다. 다른 기관 규격서에는
그 기관 사정에 맞춘 조건(특정 제조사, 지역 조건 등)이 섞여 있으므로
사람이 검토한 뒤에야 라이브러리에 들어가야 한다.
"""
from __future__ import annotations

import re
import struct
import time
import urllib.parse
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

MAX_MB_DEFAULT = 20


# ---------------------------------------------------------------- 다운로드
@dataclass
class Downloaded:
    path: Path | None
    name: str
    url: str
    size: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.path is not None and self.error == ""


# g2b 다운로드 링크는 URL에 파일명·확장자가 없다. 실제 이름은 응답 헤더에 있다.
_CD_STAR = re.compile(r"filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)", re.I)
_CD_PLAIN = re.compile(r'filename\s*=\s*"?([^";]+)"?', re.I)


def _server_filename(resp) -> str | None:
    """Content-Disposition 헤더에서 실제 파일명을 뽑는다. 없으면 None."""
    cd = resp.headers.get("Content-Disposition") or ""
    m = _CD_STAR.search(cd)
    if m:
        try:
            return urllib.parse.unquote(m.group(1)).strip().strip('"') or None
        except Exception:  # noqa: BLE001 - 헤더가 깨졌으면 다음 방식으로
            pass
    m = _CD_PLAIN.search(cd)
    if m:
        val = m.group(1).strip()
        # requests 는 헤더를 latin-1 로 디코딩한다. 한글 파일명은 그 과정에서
        # 깨지므로 UTF-8 로 되돌린다 (되돌릴 수 없으면 원문 유지).
        try:
            val = val.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        return val or None
    return None


def _has_ext(name: str, conf: dict) -> bool:
    """파일명에 허용 확장자가 붙어 있는가 (내려받기 전 판단 가능 여부)."""
    low = name.lower()
    return any(low.endswith(e) for e in conf["filters"]["허용확장자"])


def _sanitize(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


def download(url: str, name: str, out_dir: Path, conf: dict,
             session: requests.Session | None = None,
             prefix: str = "") -> Downloaded:
    s = session or requests.Session()
    s.headers["User-Agent"] = conf["collect"]["user_agent"]
    limit = int(conf["collect"].get("max_file_mb", MAX_MB_DEFAULT)) * 1024 * 1024
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        r = s.get(url, timeout=60, stream=True)
        if r.status_code != 200:
            return Downloaded(None, name, url, error=f"HTTP {r.status_code}")
        # 서버가 주는 실제 파일명을 우선한다. g2b 다운로드 링크는 URL에
        # 확장자·파일명이 없고 Content-Disposition 헤더에만 들어 있다.
        base = _sanitize(_server_filename(r) or name) or "download"
        safe = (f"{_sanitize(prefix)}_{base}" if prefix else base)[:150]
        dest = out_dir / safe
        total = 0
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(65536):
                total += len(chunk)
                if total > limit:
                    fh.close()
                    dest.unlink(missing_ok=True)
                    return Downloaded(None, safe, url,
                                      error=f"크기 초과 ({limit // 1024 // 1024}MB)")
                fh.write(chunk)
        if total == 0:
            dest.unlink(missing_ok=True)
            return Downloaded(None, safe, url, error="빈 파일")
        return Downloaded(dest, safe, url, size=total)
    except requests.RequestException as e:
        return Downloaded(None, name, url, error=f"{type(e).__name__}: {e}")
    finally:
        time.sleep(float(conf["collect"].get("download_throttle_sec", 1.5)))


# ---------------------------------------------------------------- 텍스트 추출
def extract_text(path: Path) -> tuple[str, str]:
    """(텍스트, 사용한 방법). 실패하면 ('', 사유)."""
    suf = path.suffix.lower()
    try:
        if suf == ".hwpx":
            return _from_hwpx(path), "hwpx"
        if suf == ".hwp":
            return _from_hwp(path), "hwp"
        if suf == ".pdf":
            return _from_pdf(path), "pdf"
        if suf in (".docx", ".doc"):
            return _from_docx(path), "docx"
    except Exception as e:
        return "", f"추출 실패: {type(e).__name__}: {e}"
    return "", f"지원하지 않는 형식: {suf}"


def _from_hwpx(path: Path) -> str:
    from hwpx.document import HwpxDocument
    return HwpxDocument.open(str(path)).export_text()


def _from_hwp(path: Path) -> str:
    """레거시 .hwp — OLE 컨테이너에서 BodyText 레코드를 직접 파싱한다."""
    import olefile

    f = olefile.OleFileIO(str(path))
    try:
        hdr = f.openstream("FileHeader").read()
        compressed = bool(hdr[36] & 1)
        parts: list[str] = []
        for entry in f.listdir():
            if len(entry) == 2 and entry[0] == "BodyText":
                data = f.openstream("/".join(entry)).read()
                if compressed:
                    data = zlib.decompress(data, -15)
                parts.append(_parse_hwp_section(data))
        return "\n".join(parts)
    finally:
        f.close()


def _parse_hwp_section(data: bytes) -> str:
    out: list[str] = []
    i = 0
    while i < len(data) - 3:
        h = struct.unpack("<I", data[i:i + 4])[0]
        tag = h & 0x3FF
        size = (h >> 20) & 0xFFF
        i += 4
        if size == 0xFFF:
            size = struct.unpack("<I", data[i:i + 4])[0]
            i += 4
        payload = data[i:i + size]
        i += size
        if tag != 67:                      # PARA_TEXT
            continue
        buf: list[str] = []
        j = 0
        while j < len(payload) - 1:
            c = struct.unpack("<H", payload[j:j + 2])[0]
            if c in (10, 13):
                buf.append("\n")
                j += 2
            elif c < 32:
                j += 16 if c in (1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23) else 2
                buf.append(" ")
            elif 0xD800 <= c <= 0xDFFF:
                j += 2
            else:
                buf.append(chr(c))
                j += 2
        out.append("".join(buf))
    return "\n".join(out)


def _from_pdf(path: Path) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    except ImportError:
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)


def _from_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    return re.sub(r"<[^>]+>", "", xml)


# ---------------------------------------------------------------- 조항 분해
# 절 분류 키워드. '규격'·'성능' 같은 통짜 낱말은 넣지 않는다.
# 「관련 규격 및 기준」이 2절(특기시방)로 잡히는 오분류를 막기 위해서다.
SECTION_KEYWORDS = {
    1: ["일반사항", "총칙", "일반조건", "개요", "적용범위", "적용기준",
        "관련규격", "관련기준", "용어의정의", "일반기준"],
    2: ["특기시방", "기술기준", "기술규격", "세부규격", "성능규격", "규격및성능",
        "기술요구", "요구사항", "기술사양", "세부사양", "장비규격"],
    3: ["제출물", "제출서류", "납품서류", "제출도서", "제출자료"],
    4: ["검사", "검수", "시험및검사", "품질보증", "성능시험", "입회시험"],
    5: ["하자", "보증", "유지보수", "사후관리", "무상보증"],
    6: ["기타", "특약", "보안", "안전", "교육", "기타사항"],
}

# 상위 절 표제 — "2. 특기시방", "제2장 기술기준", "Ⅱ. 특기시방"
_TOP = re.compile(
    r"^\s*(?:(?P<num>\d{1,2})\s*[.)]|제\s*(?P<jo>\d{1,2})\s*[장절]"
    r"|(?P<roman>[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ])\s*[.)]?)\s*"
    r"(?P<title>[^\n]{2,40})\s*$"
)

# 하위 조항 표제 — "2.1 네트워크 카메라", "2-1 ...", "제3조 ..."
# ★ 「가. 」「나. 」는 넣지 않는다. 규격서에서 그것은 조항이 아니라 본문 항목이다.
#    조항 경계로 잡으면 본문이 잘려 나가 쓸 수 없게 된다.
_SUB = re.compile(
    r"^\s*(?:(?P<a>\d{1,2})\s*[.\-]\s*(?P<b>\d{1,2})\s*[.)]?"
    r"|제\s*(?P<jo>\d{1,3})\s*조)\s*"
    r"(?P<title>[^\n]{2,40})\s*$"
)

_NOISE = re.compile(r"^\s*(?:-\s*\d+\s*-|페이지|page\s*\d+|\d+\s*/\s*\d+)\s*$", re.I)

_LEAD_NUM = re.compile(r"^\s*(?:\d{1,2}\s*[.\-]\s*)+\s*|^\s*[가-하]\s*[.)]\s*")


@dataclass
class Extracted:
    title: str
    section: int
    body: str
    source_file: str
    source_org: str = ""
    source_notice: str = ""

    def as_yaml_entry(self, idx: int) -> dict[str, Any]:
        return {
            "id": f"HARV-{idx:04d}",
            "절": self.section,
            "제목": self.title,
            "출처": "수집",
            "본문": self.body,
            "수집출처": {
                "기관": self.source_org or "미확인",
                "사전규격": self.source_notice or "미확인",
                "파일": self.source_file,
            },
        }


def guess_section(title: str) -> int | None:
    """제목으로 절을 추정한다. 확실하지 않으면 None."""
    t = title.replace(" ", "").replace("·", "")
    for num, words in SECTION_KEYWORDS.items():
        if any(w in t for w in words):
            return num
    return None


def _clean_title(s: str) -> str:
    return _LEAD_NUM.sub("", s).strip(" .:·-—")


def split_clauses(text: str, source_file: str,
                  org: str = "", notice: str = "",
                  min_body: int = 30, max_body: int = 2500) -> list[Extracted]:
    """
    규격서를 조항 단위로 쪼갠다.

    상위 표제(2. 특기시방)가 나오면 현재 절을 바꾸고,
    하위 조항(2.1 네트워크 카메라)은 그 절을 물려받는다.
    제목만으로 재분류하지 않는 이유 — '네트워크 카메라'라는 제목에는
    절을 알려 주는 단어가 없기 때문이다.
    """
    lines = [ln.rstrip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln.strip() and not _NOISE.match(ln)]

    out: list[Extracted] = []
    cur_sec = 6                      # 상위 표제를 못 만나면 기타
    cur_title: str | None = None
    buf: list[str] = []

    def flush():
        if cur_title and buf:
            body = "\n".join(buf).strip()
            if min_body <= len(body) <= max_body:
                out.append(Extracted(cur_title, cur_sec, body,
                                     source_file, org, notice))

    for ln in lines:
        top = _TOP.match(ln)
        sub = _SUB.match(ln)

        # 하위 표제가 더 구체적이므로 먼저 본다 ("2.1"은 _TOP 에도 걸린다)
        if sub:
            flush()
            cur_title = _clean_title(sub.group("title"))
            # "2.1" 처럼 번호 계층이 있으면 문서 구조가 우선이다.
            # 제목에 다른 절의 낱말이 섞여 있어도 상위 절을 그대로 물려받는다.
            #   예) "5. 하자보수" 아래의 "5.2 기술지원 및 교육"
            #       -> '교육' 때문에 6절로 튀지 않고 5절을 유지
            if sub.group("a"):
                try:
                    cur_sec = max(1, min(6, int(sub.group("a"))))
                except (TypeError, ValueError):
                    pass
            else:
                # "제3조" 처럼 계층이 없는 형식은 제목 힌트에 의존한다
                hinted = guess_section(cur_title)
                if hinted is not None:
                    cur_sec = hinted
            buf = []
            continue

        if top:
            title = _clean_title(top.group("title"))
            hinted = guess_section(title)
            if hinted is not None:
                # 상위 절 표제 — 절을 바꾸고, 이 줄 자체도 조항으로 시작
                flush()
                cur_sec = hinted
                cur_title = title
                buf = []
                continue
            flush()
            cur_title = title
            buf = []
            continue

        if cur_title:
            buf.append(ln)

    flush()
    return out


# ---------------------------------------------------------------- 파이프라인
@dataclass
class HarvestResult:
    downloaded: list[Downloaded] = field(default_factory=list)
    clauses: list[Extracted] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        ok = len([d for d in self.downloaded if d.ok])
        return (f"파일 {ok}/{len(self.downloaded)}건 · 조항 {len(self.clauses)}개 "
                f"· 건너뜀 {len(self.skipped)} · 실패 {len(self.failures)}")


def harvest(notices, conf: dict, out_dir: Path,
            session: requests.Session | None = None,
            progress=None) -> HarvestResult:
    from .g2b import is_spec_file

    res = HarvestResult()
    cap = int(conf["collect"].get("max_files_per_run", 50))
    files_dir = out_dir / "files"
    n = 0

    for notice in notices:
        if n >= cap:
            res.skipped.append(f"파일 수 상한 {cap}건에 도달해 중단했습니다.")
            break
        for name, url in notice.파일:
            if n >= cap:
                break
            # 파일명에 확장자가 있으면 내려받기 전에 규격서 여부를 판단한다.
            # g2b 다운로드 링크처럼 확장자가 없으면(opaque) 일단 받아서
            # Content-Disposition 의 실제 파일명으로 판단한다.
            if _has_ext(name, conf) and not is_spec_file(name, conf):
                res.skipped.append(f"{name} — 규격서가 아닌 것으로 판단")
                continue
            d = download(url, name, files_dir, conf, session,
                         prefix=notice.등록번호 or "NA")
            res.downloaded.append(d)
            n += 1
            if progress:
                progress(n, cap, d.name)
            if not d.ok:
                res.failures.append(f"{d.name} — {d.error}")
                continue
            if not is_spec_file(d.name, conf):
                res.skipped.append(f"{d.name} — 규격서가 아닌 것으로 판단(내려받은 뒤 확인)")
                continue
            text, how = extract_text(d.path)
            if not text.strip():
                res.failures.append(f"{d.name} — {how}")
                continue
            res.clauses.extend(split_clauses(
                text, source_file=d.name,
                org=notice.수요기관 or "", notice=notice.등록번호 or ""))
    return res
