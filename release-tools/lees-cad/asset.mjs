// Public release tooling: signs final artifacts, never archives the private checkout.
import {readFileSync, writeFileSync, mkdirSync, mkdtempSync} from 'node:fs';
import {join, basename} from 'node:path';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {checkArtifactNames} from './artifact-contract.mjs';
const [root, target, version, binary, ...names] = process.argv.slice(2);
const config = JSON.parse(readFileSync(new URL('./public-config.json', import.meta.url)));
if (!/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(version ?? '') || !['windows-x86_64','darwin-aarch64'].includes(target)) throw new Error('Unsupported release target/version');
checkArtifactNames(target, version, names);
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const keyDir = mkdtempSync(join(tmpdir(), 'lees-cad-signing-'));
const key = join(keyDir, 'updater.key');
writeFileSync(key, process.env.LEESCAD_UPDATER_PRIVATE_KEY, {mode: 0o600, flag: 'wx'});
const password = process.env.LEESCAD_UPDATER_PRIVATE_KEY_PASSWORD;
if (!password) throw new Error('Missing updater password');
const files = [];
for (const name of names) {
  if (basename(name) !== name || !name.startsWith(`lees-cad-`) || !name.includes(`-${version}-`) || !/\.(msi|dmg|zip|app\.tar\.gz)$/.test(name)) throw new Error('Unsafe public artifact');
  const file = join(root, name), bytes = readFileSync(file);
  if (!bytes.length || bytes.length > 512 * 1024 * 1024) throw new Error('Artifact size exceeds budget');
  const signature = `${file}.minisig`;
  for (const args of [ ['-S', '-s', key, '-m', file, '-x', signature], ['-V', '-P', config.updaterPublicKey, '-m', file, '-x', signature] ]) {
    if (spawnSync('minisign', args, {input: password + '\n', encoding: 'utf8'}).status !== 0) throw new Error('Artifact signing/verification failed');
  }
  files.push({name, size: bytes.length, sha256: sha(bytes), signature: readFileSync(signature, 'utf8')});
}
const extension = target.startsWith('windows') ? '.msi' : '.app.tar.gz';
const artifact = files.find(f => f.name.endsWith(extension));
if (!artifact) throw new Error('Updater artifact missing');
const row = {target, version, sourceRevision: process.env.LEES_CAD_BUILD_SHA, bundleId: 'io.github.lyq2010.leescad', minOs: target.startsWith('windows') ? '10.0' : '11.0', binarySha256: sha(readFileSync(binary)), signerCertificateSha256: target.startsWith('windows') ? config.windowsCertificateSha256 : null, artifact: {path: `lees-cad/releases/${version}/${artifact.name}`, size: artifact.size, sha256: artifact.sha256, signature: artifact.signature}, files};
if (!/^[a-f0-9]{40}$/.test(row.sourceRevision ?? '')) throw new Error('Source identity missing');
writeFileSync(join(root, `${target}.json`), JSON.stringify(row, null, 2) + '\n', {flag: 'wx'});
console.log(`Verified ${target}: ${files.length} final signed artifacts`);
