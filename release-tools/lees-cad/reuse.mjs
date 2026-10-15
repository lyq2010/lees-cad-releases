// Reuse only immutable verified artifacts from a successful manual CAD build.
import {appendFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {assets} from './verify.mjs';

export const repository = 'lyq2010/lees-cad-releases';
const workflowPath = '.github/workflows/lees-cad-release.yml';
const requiredJobs = ['validate', 'build-windows', 'build-macos', 'verify-artifacts'];

export function runId(value) {
  if (!/^[1-9][0-9]*$/.test(value ?? '') || !Number.isSafeInteger(Number(value))) {
    throw new Error('Invalid reuse run ID');
  }
  return Number(value);
}

export function validateRun(run, workflow, jobs, id) {
  if (run.id !== id || run.status !== 'completed' || run.conclusion !== 'success' ||
      run.event !== 'workflow_dispatch' || run.path !== workflowPath || run.workflow_id !== workflow.id ||
      run.head_branch !== 'main' || !/^[a-f0-9]{40}$/.test(run.head_sha ?? '') ||
      !Number.isSafeInteger(run.repository?.id) || run.repository.id <= 0 ||
      run.repository?.full_name !== repository || run.head_repository?.full_name !== repository ||
      run.repository?.id !== run.head_repository?.id) {
    throw new Error('Reuse requires a successful manual release run on this repository main');
  }
  for (const name of requiredJobs) {
    const matching = jobs.filter(job => job.name === name);
    if (matching.length !== 1 || matching[0].status !== 'completed' || matching[0].conclusion !== 'success') {
      throw new Error('Reuse requires successful original native builds and artifact verification');
    }
  }
}

export function selectArtifact(rows, run, now = Date.now()) {
  const matching = rows.filter(row => row.name === 'lees-cad-verified');
  if (matching.length !== 1) throw new Error('Exactly one verified artifact required');
  const a = matching[0], origin = a.workflow_run;
  if (!Number.isSafeInteger(a.id) || a.id <= 0 || a.expired !== false ||
      !Number.isFinite(Date.parse(a.expires_at)) || Date.parse(a.expires_at) <= now ||
      !Number.isSafeInteger(a.size_in_bytes) || a.size_in_bytes <= 0 || a.size_in_bytes > 2 ** 31 + 16 * 1024 ** 2 ||
      !/^sha256:[a-f0-9]{64}$/.test(a.digest ?? '') || origin?.id !== run.id ||
      origin?.repository_id !== run.repository.id || origin?.head_repository_id !== run.head_repository.id ||
      origin?.head_sha !== run.head_sha || origin?.head_branch !== 'main') {
    throw new Error('Verified artifact expired or provenance differs');
  }
  return a.id;
}

export function checkSource(payload, revision) {
  if (!/^[a-f0-9]{40}$/.test(revision ?? '') || payload.sourceRevision !== revision) {
    throw new Error('Signed artifact source differs from requested private source SHA');
  }
}

function api(path) {
  const result = spawnSync('gh', ['api', `repos/${repository}/${path}`], {encoding: 'utf8'});
  if (result.status !== 0) throw new Error('Cannot read trusted release run metadata');
  return JSON.parse(result.stdout);
}

function pages(path, field) {
  const rows = [];
  for (let page = 1; page <= 10; page++) {
    const data = api(`${path}${path.includes('?') ? '&' : '?'}per_page=100&page=${page}`);
    if (!Array.isArray(data[field])) throw new Error('Invalid run inventory');
    rows.push(...data[field]);
    if (data[field].length < 100) return rows;
  }
  throw new Error('Run inventory exceeds limit');
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  if (process.argv[2] === '--verify') {
    const verified = assets(process.argv[3]); // Ed25519, Minisign, size/hash and both platform identities.
    checkSource(verified.payload, process.argv[4]);
    console.log(JSON.stringify({payload: verified.payload, payloadSha256: verified.payloadSha256,
      assets: [...verified.files.keys()]}));
  } else {
    const id = runId(process.argv[2]);
    if (String(id) === process.env.GITHUB_RUN_ID) throw new Error('Cannot reuse current run');
    const run = api(`actions/runs/${id}`), workflow = api('actions/workflows/lees-cad-release.yml');
    validateRun(run, workflow, pages(`actions/runs/${id}/jobs?filter=latest`, 'jobs'), id);
    const artifact = selectArtifact(pages(`actions/runs/${id}/artifacts`, 'artifacts'), run);
    appendFileSync(process.env.GITHUB_OUTPUT, `run_id=${id}\nartifact_id=${artifact}\n`);
    console.log('Successful native build and immutable verified artifact provenance checked');
  }
}
