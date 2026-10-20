import {readFileSync, writeFileSync} from 'node:fs';
import {join, basename} from 'node:path';
import {createHash, createPublicKey, verify} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {checkArtifactNames} from './artifact-contract.mjs';
export const config = JSON.parse(readFileSync(new URL('./public-config.json', import.meta.url)));
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
export function manifest(file) {
  const bytes = readFileSync(file);
  if (bytes.length > 65536) throw new Error('Manifest oversized');
  const s = JSON.parse(bytes), payload = Buffer.from(s.payloadBase64, 'base64');
  const key = createPublicKey({key:Buffer.concat([Buffer.from('302a300506032b6570032100','hex'), Buffer.from(config.releasePublicKey,'base64')]), format:'der', type:'spki'});
  if (s.keyId !== config.keyId || !verify(null, payload, key, Buffer.from(s.signatureBase64, 'base64'))) throw new Error('Invalid release signature');
  const p = JSON.parse(payload);
  if (p.product !== 'lees-cad' || p.schemaVersion !== 1 || p.channel !== 'stable' || p.releaseId !== `lees-cad-v${p.version}` || !/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(p.version) || !/^[a-f0-9]{40}$/.test(p.sourceRevision)) throw new Error('Invalid release identity');
  return {payload:p, payloadSha256:sha(payload)};
}
export function assets(root) {
  const signed = manifest(join(root,'release-manifest.json')), p = signed.payload;
  if (Object.keys(p.platforms).sort().join(',') !== 'darwin-aarch64,windows-x86_64') throw new Error('Both platforms required');
  const files = new Map(), sums = [];
  for (const target of ['windows-x86_64','darwin-aarch64']) {
    const row = JSON.parse(readFileSync(join(root,`${target}.json`))), platform = p.platforms[target];
    checkArtifactNames(target, p.version, row.files?.map(item => item.name));
    for (const field of ['bundleId','minOs','binarySha256','signerCertificateSha256','artifact']) {
      if (JSON.stringify(row[field]) !== JSON.stringify(platform[field])) throw new Error('Signed platform metadata differs');
    }
    if (row.sourceRevision !== p.sourceRevision || row.version !== p.version || row.target !== target || platform.bundleId !== 'io.github.lyq2010.leescad' || platform.signerCertificateSha256 !== (target.startsWith('windows') ? config.windowsCertificateSha256 : null)) throw new Error('Platform identity mismatch');
    for (const item of row.files) {
      if (basename(item.name) !== item.name || !item.name.startsWith('lees-cad-') || !item.name.includes(`-${p.version}-`) || !/\.(msi|dmg|zip|app\.tar\.gz)$/.test(item.name)) throw new Error('Unsafe public filename');
      const file = join(root,item.name), bytes = readFileSync(file);
      if (!bytes.length || bytes.length > 512 * 1024 * 1024 || bytes.length !== item.size || sha(bytes) !== item.sha256 || readFileSync(file+'.minisig','utf8') !== item.signature) throw new Error('Public asset mismatch');
      if (spawnSync('minisign',['-V','-q','-P',config.updaterPublicKey,'-m',file,'-x',file+'.minisig']).status !== 0) throw new Error('Package signature invalid');
      files.set(item.name, file); files.set(item.name+'.minisig',file+'.minisig');
      sums.push(`${item.sha256}  ${item.name}`);
    }
    const a = platform.artifact, name = a.path.split('/').pop(), item = row.files.find(f => f.name === name);
    if (!item || a.path !== `lees-cad/releases/${p.version}/${name}` || a.size !== item.size || a.sha256 !== item.sha256 || a.signature !== item.signature || !name.endsWith(target.startsWith('windows')?'.msi':'.app.tar.gz')) throw new Error('Updater artifact differs');
    files.set(`${target}.json`,join(root,`${target}.json`));
  }
  writeFileSync(join(root,'SHA256SUMS'),sums.join('\n')+'\n');
  files.set('SHA256SUMS',join(root,'SHA256SUMS')); files.set('release-manifest.json',join(root,'release-manifest.json'));
  return {...signed, files};
}
if (process.argv[1] === new URL(import.meta.url).pathname) {
  const result = process.argv[2] === '--manifest' ? manifest(process.argv[3]) : assets(process.argv[2]);
  console.log(JSON.stringify({payload:result.payload, payloadSha256:result.payloadSha256, assets:result.files ? [...result.files.keys()] : undefined}));
}
