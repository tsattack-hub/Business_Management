import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { extractClauses, getHarvestStatus, searchNotices } from '../services/api';

const S = {
  wrap: { borderTop: '1px solid var(--border-subtle)', marginTop: '1rem', paddingTop: '1rem' },
  title: { fontSize: '0.78rem', fontWeight: 700, color: 'var(--text-secondary)', marginBottom: '0.5rem' },
  row: { display: 'flex', gap: '0.5rem', alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: '0.6rem' },
  label: { display: 'block', marginBottom: '0.2rem', fontSize: '0.72rem', color: 'var(--text-tertiary)' },
  btn: (on = true) => ({
    padding: '0.45rem 0.9rem', borderRadius: 8, border: 'none', cursor: on ? 'pointer' : 'not-allowed',
    fontSize: '0.82rem', fontWeight: 600, background: on ? 'var(--accent)' : 'var(--bg-tertiary)', color: '#fff',
  }),
  list: { maxHeight: 260, overflow: 'auto', border: '1px solid var(--border-subtle)', borderRadius: 8, padding: '0.3rem' },
  item: { display: 'flex', gap: '0.5rem', alignItems: 'flex-start', padding: '0.35rem 0.4rem', borderBottom: '1px solid var(--border-subtle)', fontSize: '0.82rem' },
  meta: { fontSize: '0.7rem', color: 'var(--text-tertiary)', marginTop: '0.1rem' },
  warn: { color: '#fca5a5', fontSize: '0.72rem', marginTop: '0.15rem' },
  info: { borderLeft: '3px solid var(--accent)', background: 'var(--bg-tertiary)', color: 'var(--text-secondary)', padding: '0.5rem 0.8rem', fontSize: '0.8rem', lineHeight: 1.6, borderRadius: 4 },
  pre: { whiteSpace: 'pre-wrap', fontSize: '0.74rem', lineHeight: 1.55, color: 'var(--text-secondary)', background: 'var(--bg-tertiary)', borderRadius: 6, padding: '0.5rem 0.7rem', margin: '0.3rem 0 0' },
};

function won(v) {
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? `${n.toLocaleString()}원` : '-';
}

// clause 를 안정적으로 식별 (제목+기관+본문 앞부분)
const clauseKey = (c) => `${c.기관 || ''}|${c.제목 || ''}|${(c.본문 || '').slice(0, 24)}`;

export default function HarvestPanel({ defaultKeyword, onSelect }) {
  const [keyConfigured, setKeyConfigured] = useState(null);
  const [keyword, setKeyword] = useState(defaultKeyword || '');
  const [days, setDays] = useState(90);
  const [searching, setSearching] = useState(false);
  const [notices, setNotices] = useState(null);
  const [pickedIds, setPickedIds] = useState(() => new Set());
  const [extracting, setExtracting] = useState(false);
  const [clauses, setClauses] = useState(null);
  const [pickedClauses, setPickedClauses] = useState(() => new Set());
  const [summary, setSummary] = useState('');
  const [error, setError] = useState(null);

  useEffect(() => {
    getHarvestStatus().then(r => setKeyConfigured(r.keyConfigured)).catch(() => setKeyConfigured(false));
  }, []);

  useEffect(() => { setKeyword(defaultKeyword || ''); }, [defaultKeyword]);

  // 고른 조항이 바뀌면 상위(초안)로 올려보낸다
  const clauseByKey = useMemo(() => {
    const m = new Map();
    (clauses || []).forEach(c => m.set(clauseKey(c), c));
    return m;
  }, [clauses]);

  useEffect(() => {
    const chosen = [...pickedClauses]
      .map(k => clauseByKey.get(k))
      .filter(Boolean)
      .map(c => ({ 제목: c.제목, 절: c.절, 본문: c.본문, 기관: c.기관, 사전규격: c.사전규격 }));
    onSelect(chosen);
  }, [pickedClauses, clauseByKey, onSelect]);

  const onSearch = useCallback(async () => {
    setSearching(true); setError(null); setNotices(null); setClauses(null);
    setPickedIds(new Set()); setPickedClauses(new Set());
    try {
      const r = await searchNotices(keyword.trim(), { days });
      setNotices(r.notices || []);
    } catch (e) {
      setError('검색 실패: ' + (e.response?.data?.detail || e.message));
    } finally {
      setSearching(false);
    }
  }, [keyword, days]);

  const toggleNotice = useCallback((id) => {
    setPickedIds(prev => {
      const s = new Set(prev);
      s.has(id) ? s.delete(id) : s.add(id);
      return s;
    });
  }, []);

  const onExtract = useCallback(async () => {
    const chosen = (notices || []).filter(n => pickedIds.has(n.등록번호));
    if (chosen.length === 0) return;
    setExtracting(true); setError(null); setClauses(null); setPickedClauses(new Set());
    try {
      const r = await extractClauses(chosen);
      setClauses(r.clauses || []);
      setSummary(r.summary || '');
    } catch (e) {
      setError('조항 추출 실패: ' + (e.response?.data?.detail || e.message));
    } finally {
      setExtracting(false);
    }
  }, [notices, pickedIds]);

  const toggleClause = useCallback((k) => {
    setPickedClauses(prev => {
      const s = new Set(prev);
      s.has(k) ? s.delete(k) : s.add(k);
      return s;
    });
  }, []);

  if (keyConfigured === null) return null;

  return (
    <div style={S.wrap}>
      <div style={S.title}>조달청 유사 규격서 검토 (선택) — 다른 기관 규격서에서 조항 후보를 가져옵니다</div>

      {!keyConfigured ? (
        <div style={S.info}>
          서버에 조달청 인증키(<code>G2B_KEY</code>)가 설정되지 않아 이 기능이 꺼져 있습니다.<br />
          백엔드를 켜기 전에 환경변수를 넣으세요:<br />
          <code>$env:G2B_KEY="발급받은_Decoding_키"</code> → <code>python -m uvicorn backend.main:app --port 8000</code>
        </div>
      ) : (
        <>
          {/* 검색 */}
          <div style={S.row}>
            <div style={{ flex: 1, minWidth: 200 }}>
              <label style={S.label}>검색어 (사업명/품목)</label>
              <input value={keyword} onChange={e => setKeyword(e.target.value)}
                placeholder="예) 양방향라디오"
                onKeyDown={e => { if (e.key === 'Enter') onSearch(); }} />
            </div>
            <div style={{ width: 96 }}>
              <label style={S.label}>기간(일)</label>
              <select value={days} onChange={e => setDays(Number(e.target.value))}>
                {[30, 90, 180, 365].map(d => <option key={d} value={d}>{d}일</option>)}
              </select>
            </div>
            <button style={S.btn(!searching && keyword.trim())} onClick={onSearch} disabled={searching || !keyword.trim()}>
              {searching ? '검색 중…' : '조달청 검색'}
            </button>
          </div>

          {/* 공고 목록 */}
          {notices && notices.length === 0 && (
            <div style={S.info}>해당 기간에 결과가 없습니다. 기간을 늘리거나 검색어를 바꿔보세요.</div>
          )}
          {notices && notices.length > 0 && (
            <>
              <div style={S.list}>
                {notices.map(n => (
                  <label key={n.등록번호} style={{ ...S.item, cursor: 'pointer' }}>
                    <input type="checkbox" checked={pickedIds.has(n.등록번호)}
                      onChange={() => toggleNotice(n.등록번호)} style={{ marginTop: '0.2rem' }} />
                    <span style={{ minWidth: 0 }}>
                      <div>{n.사업명 || '(제목 없음)'}</div>
                      <div style={S.meta}>
                        {[n.수요기관, won(n.budget), `첨부 ${n.파일수}`, n.품목군추정 && `추정 ${n.품목군추정}`, n.공개일자]
                          .filter(Boolean).join(' · ')}
                      </div>
                    </span>
                  </label>
                ))}
              </div>
              <div style={{ ...S.row, marginTop: '0.6rem' }}>
                <button style={S.btn(!extracting && pickedIds.size > 0)} onClick={onExtract}
                  disabled={extracting || pickedIds.size === 0}>
                  {extracting ? '파일 받아 조항 추출 중… (느립니다)' : `선택 ${pickedIds.size}건에서 조항 추출`}
                </button>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>
                  선택한 공고의 규격서 파일을 내려받아 조항으로 쪼갭니다. 파일당 대기가 있어 시간이 걸립니다.
                </span>
              </div>
            </>
          )}

          {/* 추출 조항 */}
          {clauses && (
            <>
              <div style={{ ...S.title, marginTop: '0.8rem' }}>
                추출 조항 {clauses.length}개 — 체크한 것만 초안에 들어갑니다 (출처=수집, 검토 필요)
                {summary && <span style={{ fontWeight: 400, color: 'var(--text-tertiary)' }}> · {summary}</span>}
              </div>
              {clauses.length === 0 && (
                <div style={S.info}>추출된 조항이 없습니다. 파일이 규격서가 아니거나(공고문 등) 텍스트 추출에 실패했을 수 있습니다.</div>
              )}
              {clauses.length > 0 && (
                <div style={{ ...S.list, maxHeight: 340 }}>
                  {clauses.map((c) => {
                    const k = clauseKey(c);
                    return (
                      <div key={k} style={S.item}>
                        <input type="checkbox" checked={pickedClauses.has(k)}
                          onChange={() => toggleClause(k)} style={{ marginTop: '0.2rem' }} />
                        <span style={{ minWidth: 0, flex: 1 }}>
                          <div><b>[{c.절}절]</b> {c.제목}</div>
                          <div style={S.meta}>{[c.기관, c.파일].filter(Boolean).join(' · ')}</div>
                          {c.브랜드경고?.length > 0 && (
                            <div style={S.warn}>
                              ⚠ 특정회사 규격 의심: {c.브랜드경고.map(h => h.term).join(', ')}
                              {' '}— 성능 수치로 바꾸거나 사유 명시 필요 (AUD-013)
                            </div>
                          )}
                          <details>
                            <summary style={{ cursor: 'pointer', fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>본문</summary>
                            <pre style={S.pre}>{c.본문}</pre>
                          </details>
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          )}

          {error && <div style={{ color: 'var(--danger)', fontSize: '0.8rem', marginTop: '0.5rem' }}>{error}</div>}
        </>
      )}
    </div>
  );
}
