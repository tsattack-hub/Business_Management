import axios from 'axios';

const api = axios.create({ baseURL: '/api' });

// ─── 사업 절차관리 ──────────────────────────────────────────────────────────────

export const listProjects = () => api.get('/projects').then(r => r.data.projects);

export const getBlank = () => api.get('/projects/blank').then(r => r.data);

export const getProject = (pid) => api.get(`/projects/${encodeURIComponent(pid)}`).then(r => r.data);

export const saveProject = (project) => api.post('/projects', project).then(r => r.data);

export const deleteProject = (pid) =>
  api.delete(`/projects/${encodeURIComponent(pid)}`).then(r => r.data);

export const analyzeProject = (project) => api.post('/projects/analyze', project).then(r => r.data);

export const downloadDocument = async (docId, project) => {
  const res = await api.post(`/projects/document/${encodeURIComponent(docId)}`, project, {
    responseType: 'blob',
  });
  _triggerDownload(res, `${docId}`);
};

export const downloadAllZip = async (project) => {
  const res = await api.post('/projects/documents-zip', project, { responseType: 'blob' });
  const made = res.headers['x-made-count'];
  _triggerDownload(res, '서류틀.zip');
  return { made: made ? Number(made) : null };
};

// ─── 구매규격서 생성 ──────────────────────────────────────────────────────────────

export const getSpecItemGroups = () =>
  api.get('/specgen/item-groups').then(r => r.data.groups);

export const buildSpecDraft = (groupId, project, specValues) =>
  api
    .post('/specgen/draft', { group_id: groupId, project, spec_values: specValues || {} })
    .then(r => r.data);

export const downloadSpecDocument = async (groupId, project, specValues) => {
  const res = await api.post(
    '/specgen/document',
    { group_id: groupId, project, spec_values: specValues || {} },
    { responseType: 'blob' },
  );
  _triggerDownload(res, '구매규격서(초안).hwpx');
};

// ─── 내역서 검증 ────────────────────────────────────────────────────────────────

export const inspectBoq = (file) => {
  const form = new FormData();
  form.append('file', file);
  return api.post('/boq/inspect', form).then(r => r.data);
};

export const checkBoq = (file, { boqSheet, qtySheet, boqMap, qtyMap }) => {
  const form = new FormData();
  form.append('file', file);
  form.append('boq_sheet', String(boqSheet));
  form.append('qty_sheet', String(qtySheet ?? -1));
  form.append('boq_map', JSON.stringify(boqMap));
  form.append('qty_map', JSON.stringify(qtyMap || {}));
  return api.post('/boq/check', form).then(r => r.data);
};

// ─── 공통 ───────────────────────────────────────────────────────────────────────

function _triggerDownload(res, fallbackName) {
  const cd = res.headers['content-disposition'] || '';
  const match = cd.match(/filename\*?=(?:UTF-8'')?([^;]+)/i);
  const name = match ? decodeURIComponent(match[1].replace(/"/g, '')) : fallbackName;
  const url = URL.createObjectURL(res.data);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}
