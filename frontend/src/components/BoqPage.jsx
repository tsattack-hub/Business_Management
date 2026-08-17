import React, { useCallback, useRef, useState } from 'react';
import { checkBoq, inspectBoq } from '../services/api';

const S = {
  card: {
    background: 'var(--bg-secondary)', borderRadius: 12, border: '1px solid var(--border-subtle)',
    padding: '1.2rem 1.4rem', marginBottom: '1rem',
  },
  drop: (drag) => ({
    border: `2px dashed ${drag ? 'var(--accent)' : 'var(--border-subtle)'}`,
    borderRadius: 10, padding: '1.6rem', textAlign: 'center', cursor: 'pointer',
    background: drag ? 'var(--accent-light)' : 'transparent', transition: 'all 0.15s',
  }),
  trap: {
    borderLeft: '3px solid var(--brick)', background: 'var(--brick-bg)', color: '#fca5a5',
    padding: '0.6rem 0.9rem', margin: '0.4rem 0', fontSize: '0.83rem', lineHeight: 1.6, borderRadius: 4,
  },
  tip: {
    borderLeft: '3px solid var(--accent)', background: 'var(--tip-bg)', color: '#93c5fd',
    padding: '0.6rem 0.9rem', margin: '0.4rem 0', fontSize: '0.83rem', lineHeight: 1.6, borderRadius: 4,
  },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' },
  th: { background: 'var(--bg-tertiary)', color: 'var(--text-secondary)', padding: '0.4rem 0.6rem', textAlign: 'left', borderBottom: '1px solid var(--border-subtle)', whiteSpace: 'nowrap' },
  td: { padding: '0.35rem 0.6rem', borderBottom: '1px solid var(--border-subtle)' },
  metric: { flex: 1, minWidth: 130, background: 'var(--bg-tertiary)', borderRadius: 10, padding: '0.8rem 1rem' },
};

const BOQ_ROLES = ['품명', '규격', '수량', '재료비단가', '재료비', '노무비단가', '노무비', '경비단가', '경비', '합계'];
const QTY_ROLES = ['품명', '규격', '수량'];

const KIND_LABEL = {
  R1: '행 금액 ≠ 수량 × 단가', R2: '합계 ≠ 재료비 + 노무비 + 경비', R3: '소계 ≠ 명세 행의 합',
  R4: 'SUM 수식 범위 누락', R5: '수식이 아닌 하드코딩', R6: '총계 ≠ 소계의 합',
  Q1: '수량 불일치', Q2: '내역서에만 있는 항목', Q3: '수량산출서에만 있는 항목',
};

function defaultMap(sheet, roles) {
  const out = {};
  for (const role of roles) {
    const col = sheet.columns.find(c => c.guess === role);
    out[role] = col ? col.index : null;
  }
  return out;
}

function num(v) {
  return v === null || v === undefined ? '-' : Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function MappingRow({ sheet, roles, map, setMap }) {
  const opts = [{ v: '', label: '— 없음 —' }, ...sheet.columns.map(c => ({ v: c.index, label: `${c.letter}. ${c.header.slice(0, 24)}` }))];
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: '0.5rem' }}>
      {roles.map(role => (
        <div key={role}>
          <label style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>{role}</label>
          <select
            value={map[role] ?? ''}
            onChange={e => setMap({ ...map, [role]: e.target.value === '' ? null : Number(e.target.value) })}
          >
            {opts.map(o => <option key={o.v} value={o.v}>{o.label}</option>)}
          </select>
        </div>
      ))}
    </div>
  );
}

export default function BoqPage() {
  const [file, setFile] = useState(null);
  const [inspect, setInspect] = useState(null);
  const [boqSheet, setBoqSheet] = useState(0);
  const [qtySheet, setQtySheet] = useState(-1);
  const [boqMap, setBoqMap] = useState({});
  const [qtyMap, setQtyMap] = useState({});
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [drag, setDrag] = useState(false);
  const [loading, setLoading] = useState(false);
  const [showMapping, setShowMapping] = useState(false);
  const inputRef = useRef();

  const onFile = useCallback(async (f) => {
    if (!f) return;
    setFile(f); setError(''); setResult(null);
    try {
      const data = await inspectBoq(f);
      setInspect(data);
      const bi = data.defaults.boqIndex ?? 0;
      const qi = data.defaults.qtyIndex ?? -1;
      setBoqSheet(bi);
      setQtySheet(qi ?? -1);
      setBoqMap(defaultMap(data.sheets[bi], BOQ_ROLES));
      setQtyMap(qi != null && qi >= 0 ? defaultMap(data.sheets[qi], QTY_ROLES) : {});
    } catch (e) {
      setError(e.response?.data?.detail || '파일을 읽지 못했습니다.');
      setInspect(null);
    }
  }, []);

  const onSelectBoqSheet = (i) => { setBoqSheet(i); setBoqMap(defaultMap(inspect.sheets[i], BOQ_ROLES)); };
  const onSelectQtySheet = (i) => {
    setQtySheet(i);
    setQtyMap(i >= 0 ? defaultMap(inspect.sheets[i], QTY_ROLES) : {});
  };

  const onCheck = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const res = await checkBoq(file, { boqSheet, qtySheet, boqMap, qtyMap });
      setResult(res);
    } catch (e) {
      setError(e.response?.data?.detail || '검증에 실패했습니다.');
    } finally { setLoading(false); }
  }, [file, boqSheet, qtySheet, boqMap, qtyMap]);

  const sheetLabel = (s) => `${s.name} (헤더 ${s.headerRow}행 · ${s.nRows}행)`;
  const boqIssues = result?.boq?.issues || [];
  const qtyIssues = result?.qty?.issues || [];
  const totalIssues = boqIssues.length + qtyIssues.length;

  return (
    <div>
      <div style={S.card}>
        <div style={{ fontSize: '1.1rem', fontWeight: 800, marginBottom: '0.3rem' }}>내역서 검증</div>
        <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '1rem' }}>
          소계·합계 검산과 수량 대조. 설계 단계에서 돌리면 감사 지적 두 건이 사라집니다.
        </div>

        <div
          style={S.drop(drag)}
          onClick={() => inputRef.current?.click()}
          onDragOver={e => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={e => { e.preventDefault(); setDrag(false); onFile(e.dataTransfer.files[0]); }}
        >
          <input ref={inputRef} type="file" accept=".xlsx" style={{ display: 'none' }}
            onChange={e => { onFile(e.target.files[0]); e.target.value = ''; }} />
          <div style={{ fontSize: '1.4rem', marginBottom: '0.3rem' }}>◫</div>
          <div style={{ color: 'var(--text-secondary)', fontSize: '0.88rem' }}>
            {file ? file.name : '내역서 (.xlsx) 파일을 올려주세요'}
          </div>
          <div style={{ color: 'var(--text-tertiary)', fontSize: '0.75rem', marginTop: '0.3rem' }}>
            수량산출서가 같은 파일에 있으면 함께 대조합니다 · 드래그앤드롭 또는 클릭
          </div>
        </div>
        {error && <div style={{ ...S.trap, marginTop: '0.8rem' }}>{error}</div>}
      </div>

      {inspect && (
        <div style={S.card}>
          <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: 220 }}>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>내역서 시트</label>
              <select value={boqSheet} onChange={e => onSelectBoqSheet(Number(e.target.value))}>
                {inspect.sheets.map((s, i) => <option key={i} value={i}>{sheetLabel(s)}</option>)}
              </select>
            </div>
            <div style={{ flex: 1, minWidth: 220 }}>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>수량산출서 시트</label>
              <select value={qtySheet} onChange={e => onSelectQtySheet(Number(e.target.value))}>
                <option value={-1}>— 대조 안 함 —</option>
                {inspect.sheets.map((s, i) => <option key={i} value={i}>{sheetLabel(s)}</option>)}
              </select>
            </div>
          </div>

          <div style={{ marginTop: '0.8rem' }}>
            <button
              onClick={() => setShowMapping(v => !v)}
              style={{ background: 'transparent', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)', padding: '0.3rem 0.7rem', borderRadius: 6, cursor: 'pointer', fontSize: '0.78rem' }}
            >
              {showMapping ? '▲ 열 매핑 숨기기' : '▼ 열 매핑 확인 · 수정'}
            </button>
          </div>

          {showMapping && (
            <div style={{ marginTop: '0.8rem' }}>
              <div style={{ fontSize: '0.8rem', fontWeight: 700, margin: '0.4rem 0' }}>내역서</div>
              <MappingRow sheet={inspect.sheets[boqSheet]} roles={BOQ_ROLES} map={boqMap} setMap={setBoqMap} />
              {qtySheet >= 0 && (
                <>
                  <div style={{ fontSize: '0.8rem', fontWeight: 700, margin: '0.8rem 0 0.4rem' }}>수량산출서</div>
                  <MappingRow sheet={inspect.sheets[qtySheet]} roles={QTY_ROLES} map={qtyMap} setMap={setQtyMap} />
                </>
              )}
              {['재료비', '노무비'].some(r => boqMap[r] == null) && (
                <div style={{ ...S.trap, marginTop: '0.6rem' }}>
                  재료비·노무비 <b>금액</b> 열이 지정되지 않았습니다. 단가 열이 아니라 금액 열입니다.
                </div>
              )}
            </div>
          )}

          <button
            onClick={onCheck} disabled={loading}
            style={{ marginTop: '1rem', background: 'var(--accent)', color: '#fff', border: 'none', padding: '0.55rem 1.2rem', borderRadius: 8, cursor: 'pointer', fontWeight: 600, fontSize: '0.88rem' }}
          >
            {loading ? '검증 중…' : '검증 실행'}
          </button>
        </div>
      )}

      {result && (
        <>
          {/* 지표 */}
          <div style={{ ...S.card, display: 'flex', gap: '0.8rem', flexWrap: 'wrap' }}>
            <div style={S.metric}>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>검산 건수</div>
              <div style={{ fontSize: '1.3rem', fontWeight: 800 }}>{result.boq.checked.toLocaleString()}건</div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)' }}>명세 {result.boq.detailRows}행 · 소계 {result.boq.subtotalRows}개</div>
            </div>
            <div style={S.metric}>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>소계·합계 불일치</div>
              <div style={{ fontSize: '1.3rem', fontWeight: 800, color: boqIssues.length ? 'var(--brick)' : 'var(--success)' }}>{boqIssues.length}건</div>
            </div>
            <div style={S.metric}>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>수량 대조</div>
              <div style={{ fontSize: '1.3rem', fontWeight: 800 }}>
                {result.qty ? `${result.qty.matched}/${result.qty.boqItems} 일치` : '미실시'}
              </div>
              {result.qty && qtyIssues.length > 0 && <div style={{ fontSize: '0.7rem', color: 'var(--brick)' }}>문제 {qtyIssues.length}건</div>}
            </div>
            <div style={S.metric}>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>전체 지적 후보</div>
              <div style={{ fontSize: '1.3rem', fontWeight: 800, color: totalIssues ? 'var(--brick)' : 'var(--success)' }}>{totalIssues}건</div>
            </div>
          </div>

          {result.boq.notes.map((n, i) => <div key={i} style={{ ...S.card, ...S.trap }}>{n}</div>)}
          {totalIssues === 0 && <div style={{ ...S.card, ...S.tip }}>검산과 대조 모두 통과했습니다.</div>}

          {/* AUD-030 소계·합계 검산 */}
          {boqIssues.length > 0 && (
            <div style={S.card}>
              <div style={{ fontWeight: 700, marginBottom: '0.6rem' }}>AUD-030 · 소계·합계 검산</div>
              {['R6', 'R5', 'R4', 'R3', 'R2', 'R1'].map(kind => {
                const group = boqIssues.filter(i => i.kind === kind);
                if (!group.length) return null;
                return (
                  <div key={kind} style={{ marginBottom: '1rem' }}>
                    <div style={{ fontSize: '0.85rem', fontWeight: 600, margin: '0.4rem 0' }}>{KIND_LABEL[kind]} ({group.length}건)</div>
                    <div style={{ overflowX: 'auto' }}>
                      <table style={S.table}>
                        <thead><tr>{['셀', '항목', '기댓값', '실제값', '차액', '내용'].map(h => <th key={h} style={S.th}>{h}</th>)}</tr></thead>
                        <tbody>
                          {group.map((i, k) => (
                            <tr key={k}>
                              <td style={S.td}>{i.where}</td>
                              <td style={S.td}>{i.label}</td>
                              <td style={S.td}>{num(i.expected)}</td>
                              <td style={S.td}>{num(i.actual)}</td>
                              <td style={{ ...S.td, color: 'var(--brick)' }}>{i.diff == null ? '-' : (i.diff > 0 ? '+' : '') + num(i.diff)}</td>
                              <td style={S.td}>{i.message}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* AUD-014 수량 대조 */}
          {result.qty && qtyIssues.length > 0 && (
            <div style={S.card}>
              <div style={{ fontWeight: 700, marginBottom: '0.6rem' }}>AUD-014 · 수량 대조</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)', marginBottom: '0.5rem' }}>
                내역서 {result.qty.boqItems}개 · 수량산출서 {result.qty.qtyItems}개 · 일치 {result.qty.matched}개
              </div>
              {['Q1', 'Q2', 'Q3'].map(kind => {
                const group = qtyIssues.filter(i => i.kind === kind);
                if (!group.length) return null;
                return (
                  <div key={kind} style={{ marginBottom: '1rem' }}>
                    <div style={{ fontSize: '0.85rem', fontWeight: 600, margin: '0.4rem 0' }}>{KIND_LABEL[kind]} ({group.length}건)</div>
                    <div style={{ overflowX: 'auto' }}>
                      <table style={S.table}>
                        <thead><tr>{['항목', '내역서', '수량산출서', '내용'].map(h => <th key={h} style={S.th}>{h}</th>)}</tr></thead>
                        <tbody>
                          {group.map((i, k) => (
                            <tr key={k}>
                              <td style={S.td}>{i.label}</td>
                              <td style={S.td}>{i.actual == null ? '없음' : num(i.actual)}</td>
                              <td style={S.td}>{i.expected == null ? '없음' : num(i.expected)}</td>
                              <td style={S.td}>{i.message}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* 요약 findings */}
          {result.findings.length > 0 && (
            <div style={S.card}>
              <div style={{ fontWeight: 700, marginBottom: '0.6rem' }}>요약</div>
              {result.findings.map((f, i) => (
                <div key={i} style={f.passed ? S.tip : S.trap}>
                  <b>{f.ruleId} · {f.name}</b><br />{f.message}
                  {f.citation && <div style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)', marginTop: '0.3rem' }}>{f.citation}</div>}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
