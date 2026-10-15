import test from 'node:test';
import assert from 'node:assert/strict';
import {generateKeyPairSync, sign} from 'node:crypto';
import {mkdtempSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {repository, runId, validateRun, selectArtifact, checkSource} from './reuse.mjs';
import {config, manifest} from './verify.mjs';

const sha = 'a'.repeat(40);
const run = {id: 123, status: 'completed', conclusion: 'success', event: 'workflow_dispatch',
  path: '.github/workflows/lees-cad-release.yml', workflow_id: 456, head_branch: 'main', head_sha: sha,
  repository: {id: 789, full_name: repository}, head_repository: {id: 789, full_name: repository}};
const jobs = ['validate', 'build-windows', 'build-macos', 'verify-artifacts'].map(name =>
  ({name, status: 'completed', conclusion: 'success'}));
const artifact = {id: 999, name: 'lees-cad-verified', expired: false, expires_at: '2030-01-01T00:00:00Z',
  size_in_bytes: 1234, digest: `sha256:${'b'.repeat(64)}`,
  workflow_run: {id: 123, repository_id: 789, head_repository_id: 789, head_sha: sha, head_branch: 'main'}};

test('original native build provenance and exact immutable artifact accepted', () => {
  validateRun(run, {id: 456}, jobs, 123);
  assert.equal(selectArtifact([artifact], run), 999);
  checkSource({sourceRevision: sha}, sha);
  assert.equal(runId('123'), 123);
});

test('invalid run IDs fail before any API access', () => {
  for (const id of ['', '0', '-1', '1/../../', '1;echo x', '1.5', '1e3', '9007199254740992']) {
    assert.throws(() => runId(id));
  }
});

test('wrong run, failure, non-manual trigger, branch and workflow rejected', () => {
  for (const change of [{id: 124}, {status: 'in_progress'}, {conclusion: 'failure'},
    {event: 'pull_request'}, {path: '.github/workflows/other.yml'}, {workflow_id: 457},
    {head_branch: 'feature'}, {head_sha: 'invalid'},
    {repository: {...run.repository, full_name: 'other/repo'}},
    {head_repository: {id: 888, full_name: 'fork/repo'}}]) {
    assert.throws(() => validateRun({...run, ...change}, {id: 456}, jobs, 123));
  }
});

test('skipped, failed, missing or duplicate native jobs cannot be reused', () => {
  for (const name of ['build-windows', 'build-macos', 'verify-artifacts']) {
    for (const conclusion of ['skipped', 'failure', 'cancelled']) {
      assert.throws(() => validateRun(run, {id: 456}, jobs.map(j => j.name === name ? {...j, conclusion} : j), 123));
    }
    assert.throws(() => validateRun(run, {id: 456}, jobs.filter(j => j.name !== name), 123));
  }
  assert.throws(() => validateRun(run, {id: 456}, [...jobs, jobs[1]], 123));
});

test('expired, foreign, ambiguous, oversized or digestless artifacts rejected', () => {
  assert.throws(() => selectArtifact([], run));
  assert.throws(() => selectArtifact([artifact, artifact], run));
  for (const change of [{expired: true}, {expires_at: '2000-01-01'}, {expires_at: 'bad'},
    {size_in_bytes: 0}, {size_in_bytes: 2 ** 32}, {digest: ''}, {id: -1},
    {name: 'lees-cad-windows'}, {workflow_run: {...artifact.workflow_run, id: 124}},
    {workflow_run: {...artifact.workflow_run, head_sha: 'c'.repeat(40)}},
    {workflow_run: {...artifact.workflow_run, repository_id: 888}},
    {workflow_run: {...artifact.workflow_run, head_repository_id: 888}},
    {workflow_run: {...artifact.workflow_run, head_branch: 'feature'}}]) {
    assert.throws(() => selectArtifact([{...artifact, ...change}], run));
  }
});

test('signed private source must match exactly; release tools SHA cannot substitute', () => {
  assert.throws(() => checkSource({sourceRevision: sha}, 'c'.repeat(40)));
  assert.throws(() => checkSource({}, sha));
  assert.throws(() => checkSource({sourceRevision: ''}, ''));
});

test('actual Ed25519 verifier rejects tampered reused manifests', () => {
  const root = mkdtempSync(join(tmpdir(), 'lees-cad-reuse-test-'));
  const file = join(root, 'manifest.json'), keys = generateKeyPairSync('ed25519');
  const previousKey = config.releasePublicKey;
  try {
    config.releasePublicKey = keys.publicKey.export({type: 'spki', format: 'der'}).subarray(-32).toString('base64');
    const payload = Buffer.from(JSON.stringify({product: 'lees-cad', schemaVersion: 1, channel: 'stable',
      releaseId: 'lees-cad-v0.1.3', version: '0.1.3', sourceRevision: sha}));
    const signed = {keyId: config.keyId, payloadBase64: payload.toString('base64'),
      signatureBase64: sign(null, payload, keys.privateKey).toString('base64')};
    writeFileSync(file, JSON.stringify(signed));
    checkSource(manifest(file).payload, sha);
    assert.throws(() => checkSource(manifest(file).payload, 'c'.repeat(40)));
    writeFileSync(file, JSON.stringify({...signed, payloadBase64: Buffer.from(payload.toString().replace(sha, 'c'.repeat(40))).toString('base64')}));
    assert.throws(() => manifest(file), /signature/);
    writeFileSync(file, JSON.stringify({...signed, signatureBase64: Buffer.alloc(64).toString('base64')}));
    assert.throws(() => manifest(file), /signature/);
  } finally {
    config.releasePublicKey = previousKey;
  }
});
